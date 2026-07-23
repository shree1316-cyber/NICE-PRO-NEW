"""Small, serialisable contracts shared by the ML-shadow pipeline."""

from dataclasses import dataclass
from datetime import datetime

from nice_pro.models.market import MarketRegime, Side


@dataclass(frozen=True, slots=True)
class FeatureRow:
    """Features known at ``as_of``.  It must never contain future data."""

    as_of: datetime
    symbol: str
    side: Side
    regime: MarketRegime
    values: dict[str, float]


@dataclass(frozen=True, slots=True)
class TripleBarrierLabel:
    """Outcome of a fixed-risk, future-only research label."""

    value: int
    result: str
    entry: float
    stop: float
    target: float
    resolved_at: datetime


@dataclass(frozen=True, slots=True)
class LabeledSample:
    features: FeatureRow
    label: TripleBarrierLabel
