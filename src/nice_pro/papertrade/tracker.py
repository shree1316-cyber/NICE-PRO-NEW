"""Durable, conservative paper-forward tracker for NICE-PRO."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from nice_pro.engines.indicators import IST
from nice_pro.journal.store import ActivePaperPosition, ResearchJournal
from nice_pro.models.market import ConvictionSnapshot, OptionChainSnapshot, TradePlan
from nice_pro.papertrade.policy import ForwardTestPolicy


@dataclass(slots=True)
class _ActivePaperTrade:
    journal_open_id: int
    plan: TradePlan
    opened_at: datetime
    source: str
    policy_id: str | None
    decision_id: int | None


class PaperTradeTracker:
    """Track one conservative paper position per market without placing orders.

    When an explicit ``ForwardTestPolicy`` is supplied, only a fresh completed
    five-minute decision can open a position.  The tracker also restores active
    policy positions after an app restart so a restart cannot erase the
    simulated outcome.

    Passing no policy preserves the original permissive tracker for small unit
    tests and legacy experiments.  The desktop application always supplies the
    controlled forward-test policy.
    """

    def __init__(
        self, journal: ResearchJournal, policy: ForwardTestPolicy | None = None
    ) -> None:
        self._journal = journal
        self._policy = policy
        self._active: dict[str, _ActivePaperTrade] = {}
        if policy is not None:
            self._restore_active_positions()

    @property
    def policy(self) -> ForwardTestPolicy | None:
        return self._policy

    def evaluate(
        self,
        conviction: ConvictionSnapshot,
        chain: OptionChainSnapshot,
        decision_id: int | None,
    ) -> None:
        """Close first, then consider one fresh policy-qualified opening."""
        now = chain.calculated_at
        active = self._active.get(conviction.underlying)
        if active is not None:
            self._evaluate_active(active, chain, now)
            # A position that closed on this quote must never be re-opened from
            # the same event/candle.  The next eligible *completed 5m* decision
            # will be considered on a later call.
            return

        plan = conviction.plan
        if plan is None:
            return
        if self._policy is None:
            self._open(plan, "MTF_CONVICTION", decision_id, None)
            return
        if decision_id is None:
            return

        rejection = self._policy.entry_reason(conviction, now)
        if rejection is not None:
            return
        session_date = now.astimezone(IST).date()
        entries_today = self._journal.paper_open_count(
            self._policy.source, conviction.underlying, session_date
        )
        if entries_today >= self._policy.max_trades_per_day:
            return
        last_closed = self._journal.last_paper_close_at(
            self._policy.source, conviction.underlying
        )
        if last_closed is not None and now < self._policy.cooldown_until(last_closed):
            return
        self._open(plan, self._policy.source, decision_id, self._policy.policy_id)

    def active_plan(self, underlying: str) -> TradePlan | None:
        active = self._active.get(underlying)
        return active.plan if active is not None else None

    def active_position(self, underlying: str) -> ActivePaperPosition | None:
        """Return the active position in a presentation-safe immutable form."""
        active = self._active.get(underlying)
        if active is None:
            return None
        return ActivePaperPosition(
            journal_open_id=active.journal_open_id,
            opened_at=active.opened_at,
            plan=active.plan,
            source=active.source,
            policy_id=active.policy_id,
            decision_id=active.decision_id,
        )

    def policy_status(
        self, underlying: str, now: datetime | None = None
    ) -> dict[str, object]:
        """Expose transparent forward-test controls to the dashboard."""
        if self._policy is None:
            return {"enabled": False, "label": "Legacy paper tracker (no forward policy)"}
        current = now or datetime.now(timezone.utc)
        session_date = current.astimezone(IST).date()
        entries_today = self._journal.paper_open_count(
            self._policy.source, underlying, session_date
        )
        last_closed = self._journal.last_paper_close_at(self._policy.source, underlying)
        cooldown_until = self._policy.cooldown_until(last_closed) if last_closed else None
        active = self.active_position(underlying)
        return {
            "enabled": self._policy.enabled,
            "market_eligible": underlying in self._policy.eligible_underlyings,
            "policy_id": self._policy.policy_id,
            "source": self._policy.source,
            "minimum_mtf_score": self._policy.minimum_mtf_score,
            "minimum_grade": self._policy.minimum_grade.value,
            "cooldown_minutes": self._policy.cooldown_minutes,
            "max_trades_per_day": self._policy.max_trades_per_day,
            "entries_today": entries_today,
            "active": active is not None,
            "active_symbol": active.plan.option_symbol if active else None,
            "cooldown_until": cooldown_until,
            "entry_window": f"{self._policy.entry_start:%H:%M}–{self._policy.entry_end:%H:%M} IST",
            "force_exit_time": f"{self._policy.force_exit_time:%H:%M} IST",
        }

    def _restore_active_positions(self) -> None:
        assert self._policy is not None
        for position in self._journal.active_paper_positions(self._policy.source):
            previous = self._active.get(position.plan.underlying)
            if previous is not None and previous.opened_at >= position.opened_at:
                continue
            self._active[position.plan.underlying] = _ActivePaperTrade(
                journal_open_id=position.journal_open_id,
                plan=position.plan,
                opened_at=position.opened_at,
                source=position.source,
                policy_id=position.policy_id,
                decision_id=position.decision_id,
            )

    def _open(
        self,
        plan: TradePlan,
        source: str,
        decision_id: int | None,
        policy_id: str | None,
    ) -> None:
        open_id = self._journal.record_paper_open(plan, source, decision_id, policy_id)
        self._active[plan.underlying] = _ActivePaperTrade(
            journal_open_id=open_id,
            plan=plan,
            opened_at=datetime.now(timezone.utc),
            source=source,
            policy_id=policy_id,
            decision_id=decision_id,
        )

    def _evaluate_active(
        self,
        active: _ActivePaperTrade,
        chain: OptionChainSnapshot,
        now: datetime,
    ) -> None:
        price = next(
            (
                metric.last_price
                for metric in chain.metrics
                if metric.contract.symbol == active.plan.option_symbol
            ),
            None,
        )
        if price is None:
            return
        # If NICE-PRO was closed before its normal 15:20 exit, do not allow an
        # old paper trade to leak into a new market session.  The first quote
        # after restart is the only honest recovery price available, and its
        # exit reason remains visible in the journal.
        if active.opened_at.astimezone(IST).date() < now.astimezone(IST).date():
            self._close(active, price, price, "TIME_EXIT", "STALE_SESSION_RECOVERY")
            return
        if self._policy is not None and self._policy.should_force_exit(now):
            self._close(active, price, price, "TIME_EXIT", "FORCED_EOD_EXIT")
            return
        if price <= active.plan.stop_loss:
            # The observed quote can be below a stop in a fast move.  Use the
            # worse of it and the planned stop: no favourable stop-fill bias.
            self._close(active, min(price, active.plan.stop_loss), price, "LOSS", "STOP_LOSS")
        elif price >= active.plan.target_1:
            # Do not credit price improvement beyond Target 1 without an order
            # simulation; Target 1 is the conservative model fill.
            self._close(active, active.plan.target_1, price, "WIN", "TARGET_1")

    def _close(
        self,
        active: _ActivePaperTrade,
        fill_price: float,
        observed_price: float,
        outcome: str,
        exit_reason: str,
    ) -> None:
        self._journal.record_paper_close(
            active.journal_open_id,
            active.plan,
            fill_price,
            outcome,
            exit_reason,
            observed_price=observed_price,
            source=active.source,
            policy_id=active.policy_id,
        )
        self._active.pop(active.plan.underlying, None)
