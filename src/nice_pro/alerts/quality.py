"""Policy-safe, cooldown-protected paper-trade alerts.

An alert is deliberately stricter than a coloured dashboard recommendation.
It is emitted only when the currently selected forward-test policy has opened
the exact, fresh decision as a paper position.  This prevents an unvalidated
market, a stale option chain, or a rejected candidate from sounding like an
actionable setup.
"""

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from nice_pro.models.market import ConvictionSnapshot, OptionChainSnapshot, TradeGrade

if TYPE_CHECKING:
    from nice_pro.papertrade.policy import ForwardTestPolicy


class QualityAlertEngine:
    """Emit a sound only for an opened, policy-qualified paper trade.

    ``should_alert`` defaults to deny.  The caller must prove that a fresh
    completed-decision was accepted by the active forward policy.  Keeping the
    evidence explicit prevents desktop alerts from bypassing execution rules.
    """

    def __init__(
        self,
        cooldown_seconds: int = 300,
        max_chain_age_seconds: int = 15,
        max_quote_age_seconds: int = 10,
    ) -> None:
        self._cooldown = timedelta(seconds=cooldown_seconds)
        self._max_chain_age = timedelta(seconds=max_chain_age_seconds)
        self._max_quote_age = timedelta(seconds=max_quote_age_seconds)
        self._last_alert: dict[str, datetime] = {}

    def should_alert(
        self,
        snapshot: ConvictionSnapshot,
        *,
        policy: "ForwardTestPolicy | None" = None,
        decision_id: int | None = None,
        active_decision_id: int | None = None,
        chain: OptionChainSnapshot | None = None,
        now: datetime | None = None,
    ) -> bool:
        """Return ``True`` only for a fresh, opened policy paper position.

        ``active_decision_id`` is supplied by ``PaperTradeTracker`` after it
        evaluates the decision.  Matching it to ``decision_id`` confirms that
        the policy did not reject the candidate because of market validation,
        time window, risk, cooldown, or daily entry limits.
        """
        if snapshot.grade not in {TradeGrade.A, TradeGrade.A_PLUS} or snapshot.plan is None:
            return False
        if policy is None or decision_id is None or active_decision_id != decision_id:
            return False
        observed_at = now or datetime.now(timezone.utc)
        if policy.entry_reason(snapshot, observed_at, chain) is not None:
            return False
        if not self._has_fresh_plan_quote(
            snapshot, chain, observed_at, policy.minimum_chain_coverage
        ):
            return False

        previous = self._last_alert.get(snapshot.underlying)
        if previous is not None and observed_at - previous < self._cooldown:
            return False
        self._last_alert[snapshot.underlying] = observed_at
        return True

    def _has_fresh_plan_quote(
        self,
        snapshot: ConvictionSnapshot,
        chain: OptionChainSnapshot | None,
        observed_at: datetime,
        minimum_coverage: float,
    ) -> bool:
        """Require complete nearest-expiry coverage and a fresh selected option."""
        if chain is None or chain.underlying != snapshot.underlying:
            return False
        if not self._is_recent(chain.calculated_at, observed_at, self._max_chain_age):
            return False
        if chain.registered_contracts <= 0:
            return False
        if chain.quoted_contracts / chain.registered_contracts < minimum_coverage:
            return False
        if chain.atm_quote_age_seconds is None or chain.atm_quote_age_seconds > self._max_quote_age.total_seconds():
            return False

        plan_symbol = snapshot.plan.option_symbol
        metric = next((item for item in chain.metrics if item.contract.symbol == plan_symbol), None)
        if metric is None or metric.last_price <= 0 or metric.quote_received_at is None:
            return False
        return self._is_recent(metric.quote_received_at, observed_at, self._max_quote_age)

    @staticmethod
    def _is_recent(timestamp: datetime, now: datetime, maximum_age: timedelta) -> bool:
        """Treat naive provider timestamps as UTC and reject future/stale data."""
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        age = now - timestamp
        return timedelta(0) <= age <= maximum_age

    @staticmethod
    def play(grade: TradeGrade) -> None:
        """Best-effort sound; a missing audio device never stops the application."""
        try:
            import winsound

            if grade is TradeGrade.A_PLUS:
                for _ in range(3):
                    winsound.Beep(1200, 180)
            else:
                winsound.Beep(950, 180)
        except (ImportError, RuntimeError):
            return
