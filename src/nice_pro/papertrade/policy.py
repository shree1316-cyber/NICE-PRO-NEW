"""Forward-test rules derived from the selected 308-session core candidate.

The policy deliberately controls *whether* a core paper trade may be opened.
It does not pretend that a candle-only ATR stop can be converted exactly into
an option-premium stop.  Option execution outcomes remain a separate,
conservatively recorded forward-test layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from nice_pro.engines.indicators import IST
from nice_pro.models.market import ConvictionSnapshot, Side, TradeGrade


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

    @property
    def source(self) -> str:
        return f"FORWARD_TEST:{self.policy_id}"

    def entry_reason(self, snapshot: ConvictionSnapshot, now: datetime) -> str | None:
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
