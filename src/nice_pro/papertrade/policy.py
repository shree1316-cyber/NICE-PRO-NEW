"""Forward-test rules derived from the selected 308-session core candidate.

The policy deliberately controls *whether* a core paper trade may be opened.
It does not pretend that a candle-only ATR stop can be converted exactly into
an option-premium stop.  Option execution outcomes remain a separate,
conservatively recorded forward-test layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from nice_pro.engines.indicators import IST
from nice_pro.models.market import (
    ConvictionSnapshot,
    OptionChainSnapshot,
    OptionType,
    Side,
    TradeGrade,
)


@dataclass(frozen=True, slots=True)
class ForwardTestPolicy:
    """Paper-only entry discipline for the selected NIFTY core candidate."""

    policy_id: str = "NIFTY_CORE_308D_V1"
    enabled: bool = True
    eligible_underlyings: tuple[str, ...] = ("NIFTY",)
    minimum_mtf_score: int = 65
    minimum_grade: TradeGrade = TradeGrade.A
    cooldown_minutes: int = 15
    max_trades_per_day: int = 3
    entry_start: time = time(9, 30)
    entry_end: time = time(14, 45)
    force_exit_time: time = time(15, 20)
    minimum_chain_coverage: float = 0.95
    max_chain_age_seconds: float = 15.0
    max_atm_quote_age_seconds: float = 10.0

    @property
    def source(self) -> str:
        return f"FORWARD_TEST:{self.policy_id}"

    def entry_reason(
        self,
        snapshot: ConvictionSnapshot,
        now: datetime,
        chain: OptionChainSnapshot | None = None,
    ) -> str | None:
        """Return a human-readable rejection reason, or ``None`` when valid."""
        if not self.enabled:
            return "Forward-test policy is disabled"
        if snapshot.underlying not in self.eligible_underlyings:
            return f"No separately validated 308-session candidate for {snapshot.underlying}"
        local_time = now.astimezone(IST).time()
        if not self.entry_start <= local_time <= self.entry_end:
            return "Outside forward-test entry window"
        if snapshot.side is Side.NEUTRAL or snapshot.plan is None:
            return "No eligible MTF paper plan"
        if _grade_rank(snapshot.grade) < _grade_rank(self.minimum_grade):
            return f"Grade {snapshot.grade} is below required {self.minimum_grade}"
        score = max(snapshot.mtf_bullish_score, snapshot.mtf_bearish_score)
        if score < self.minimum_mtf_score:
            return f"MTF score {score} is below required {self.minimum_mtf_score}"
        if snapshot.mtf_alignment in {"BLOCKED / WAIT", "CORE ONLY"}:
            return f"MTF gate is {snapshot.mtf_alignment}"
        if snapshot.entry_timing == "CONFLICT":
            return "10s/30s entry timing conflicts"
        if chain is not None:
            return self.chain_reason(snapshot, chain, now)
        return None

    def chain_reason(
        self,
        snapshot: ConvictionSnapshot,
        chain: OptionChainSnapshot,
        now: datetime,
    ) -> str | None:
        """Validate the actual chain used to create a paper option plan.

        Deep OTM contracts may legitimately be quiet for several seconds, so
        this requires near-complete initial coverage plus fresh ATM/plan quotes,
        rather than incorrectly demanding a new tick from every strike.
        """
        if chain.underlying != snapshot.underlying:
            return "Option chain belongs to a different market"
        if chain.registered_contracts < 2:
            return "Nearest-expiry option chain is not registered"
        coverage = chain.quoted_contracts / chain.registered_contracts
        if coverage < self.minimum_chain_coverage:
            return f"Option-chain quote coverage {coverage:.0%} is below required {self.minimum_chain_coverage:.0%}"
        if not _is_recent(chain.calculated_at, now, self.max_chain_age_seconds):
            return "Option-chain snapshot is stale"
        if chain.atm_strike is None:
            return "ATM strike is unavailable"
        atm_types = {
            metric.contract.option_type
            for metric in chain.metrics
            if metric.contract.strike == chain.atm_strike
            and metric.last_price > 0
            and metric.quote_received_at is not None
            and _is_recent(metric.quote_received_at, now, self.max_atm_quote_age_seconds)
        }
        if {OptionType.CALL, OptionType.PUT} - atm_types:
            return "Fresh ATM call and put quotes are required"
        plan = snapshot.plan
        plan_metric = next(
            (metric for metric in chain.metrics if metric.contract.symbol == plan.option_symbol),
            None,
        )
        if (
            plan_metric is None
            or plan_metric.last_price <= 0
            or plan_metric.quote_received_at is None
            or not _is_recent(plan_metric.quote_received_at, now, self.max_atm_quote_age_seconds)
        ):
            return "Selected ATM option quote is stale or unavailable"
        return None

    def cooldown_until(self, closed_at: datetime) -> datetime:
        return closed_at + timedelta(minutes=self.cooldown_minutes)

    def should_force_exit(self, now: datetime) -> bool:
        return now.astimezone(IST).time() >= self.force_exit_time


def _grade_rank(grade: TradeGrade) -> int:
    return {
        TradeGrade.AVOID: 0,
        TradeGrade.C: 1,
        TradeGrade.B: 2,
        TradeGrade.A: 3,
        TradeGrade.A_PLUS: 4,
    }[grade]


def _is_recent(timestamp: datetime, now: datetime, maximum_age_seconds: float) -> bool:
    """Return true for a non-future provider timestamp within the allowed age."""
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age = now - timestamp
    return timedelta(0) <= age <= timedelta(seconds=maximum_age_seconds)
