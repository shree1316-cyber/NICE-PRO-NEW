"""Stable data contracts shared across the application."""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


class MarketRegime(StrEnum):
    INSUFFICIENT_DATA = "INSUFFICIENT DATA"
    TREND_UP = "TREND UP"
    TREND_DOWN = "TREND DOWN"
    RANGE = "RANGE"
    VOLATILE = "VOLATILE"


@dataclass(frozen=True, slots=True)
class Quote:
    instrument_token: int
    symbol: str
    last_price: float
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    volume: int | None = None
    bid: float | None = None
    ask: float | None = None
    open_interest: int | None = None
    last_quantity: int | None = None
    top_bid_quantity: int | None = None
    top_ask_quantity: int | None = None
    bid_depth_quantity: int | None = None
    ask_depth_quantity: int | None = None


class OptionType(StrEnum):
    CALL = "CE"
    PUT = "PE"


class TradeGrade(StrEnum):
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    AVOID = "AVOID"


@dataclass(frozen=True, slots=True)
class OptionContract:
    instrument_token: int
    symbol: str
    underlying: str
    expiry: date
    strike: float
    option_type: OptionType
    lot_size: int = 1


@dataclass(frozen=True, slots=True)
class OptionMetric:
    contract: OptionContract
    last_price: float
    open_interest: int | None
    open_interest_change: int | None
    implied_volatility: float | None
    premium_velocity: float | None
    bid: float | None = None
    ask: float | None = None
    top_bid_quantity: int | None = None
    top_ask_quantity: int | None = None
    bid_depth_quantity: int | None = None
    ask_depth_quantity: int | None = None
    estimated_cvd: int | None = None
    # Retained so every displayed chain field can be checked for freshness.
    # A quote timestamp is data provenance, not an exchange trade timestamp.
    quote_received_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class OptionChainSnapshot:
    underlying: str
    calculated_at: datetime
    spot: float | None
    atm_strike: float | None
    put_call_ratio_oi: float | None
    metrics: tuple[OptionMetric, ...] = ()
    # The current application subscribes to every strike of the nearest active
    # expiry where Kite's 3,000-token WebSocket capacity permits it. These
    # values cover that expiry, not every later monthly expiry.
    observed_max_pain: float | None = None
    iv_skew: float | None = None
    expected_move: float | None = None
    observed_strikes: tuple[float, ...] = ()
    atm_bid_ask_spread: float | None = None
    atm_book_imbalance: float | None = None
    atm_estimated_cvd: int | None = None
    otm_continuation: float | None = None
    # Coverage is deliberately explicit.  A nearest-expiry chain is complete
    # only once every registered contract has supplied a fresh quote.
    registered_contracts: int = 0
    quoted_contracts: int = 0
    fresh_contracts: int = 0
    oldest_quote_age_seconds: float | None = None
    atm_quote_age_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class TradePlan:
    underlying: str
    side: Side
    option_symbol: str
    entry: float
    stop_loss: float
    target_1: float
    target_2: float
    max_loss_per_lot: float
    lot_size: int
    note: str = "Paper-trade setup only; no order is submitted."


@dataclass(frozen=True, slots=True)
class OptionHeroSnapshot:
    """Paper-only conviction derived solely from the nearest-expiry option chain."""

    underlying: str
    calculated_at: datetime
    side: Side
    bullish_score: int
    bearish_score: int
    confidence: int
    grade: TradeGrade
    reasons: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    plan: TradePlan | None = None


@dataclass(frozen=True, slots=True)
class ScalpSnapshot:
    """Short-horizon, paper-only option scalp assessment."""

    underlying: str
    calculated_at: datetime
    side: Side
    score: int
    confidence: int
    reasons: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    plan: TradePlan | None = None
    # ``side`` is the safe, execution-facing direction. ``raw_side`` remains
    # visible for research when option-flow evidence disagrees with timing.
    raw_side: Side = Side.NEUTRAL
    setup_status: str = "BLOCKED"


@dataclass(frozen=True, slots=True)
class ConvictionSnapshot:
    underlying: str
    calculated_at: datetime
    side: Side
    bullish_score: int
    bearish_score: int
    confidence: int
    grade: TradeGrade
    bullish_reasons: tuple[str, ...] = ()
    bearish_reasons: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    plan: TradePlan | None = None
    # Multi-timeframe fields are kept separate from the compact 1-minute
    # evidence score.  This prevents a large number of correlated readings
    # from being silently added together as if they were independent votes.
    mtf_bullish_score: int = 0
    mtf_bearish_score: int = 0
    mtf_alignment: str = "CORE ONLY"
    entry_timing: str = "NOT ASSESSED"
    timeframe_signals: tuple["TimeframeSignal", ...] = ()
    # The 5-minute snapshot is the stable audit model.  The multi-timeframe
    # gate still combines all horizons before a paper plan is eligible.
    core_timeframe_seconds: int = 300


@dataclass(frozen=True, slots=True)
class TimeframeSignal:
    """One transparent directional observation used by the MTF trade gate."""

    timeframe_seconds: int
    label: str
    side: Side
    weight: int
    reason: str


@dataclass(frozen=True, slots=True)
class Candle:
    symbol: str
    timeframe_seconds: int
    opened_at: datetime
    closed_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


@dataclass(frozen=True, slots=True)
class IndicatorSnapshot:
    symbol: str
    regime: MarketRegime
    calculated_at: datetime
    timeframe_seconds: int = 60
    close: float | None = None
    vwap: float | None = None
    ema_fast: float | None = None
    ema_slow: float | None = None
    rsi: float | None = None
    atr: float | None = None
    relative_volume: float | None = None
    opening_range_high: float | None = None
    opening_range_low: float | None = None
    reasons: tuple[str, ...] = ()
    readings: tuple["IndicatorReading", ...] = ()


@dataclass(frozen=True, slots=True)
class IndicatorReading:
    """One transparent row in the live indicator matrix."""

    name: str
    category: str
    value: str
    state: str
    reason: str


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    quotes: dict[str, Quote] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def quote_for(self, symbol: str) -> Quote | None:
        return self.quotes.get(symbol)
