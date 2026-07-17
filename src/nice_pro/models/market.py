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


class OptionType(StrEnum):
    CALL = "CE"
    PUT = "PE"


@dataclass(frozen=True, slots=True)
class OptionContract:
    instrument_token: int
    symbol: str
    underlying: str
    expiry: date
    strike: float
    option_type: OptionType


@dataclass(frozen=True, slots=True)
class OptionMetric:
    contract: OptionContract
    last_price: float
    open_interest: int | None
    open_interest_change: int | None
    implied_volatility: float | None
    premium_velocity: float | None


@dataclass(frozen=True, slots=True)
class OptionChainSnapshot:
    underlying: str
    calculated_at: datetime
    spot: float | None
    atm_strike: float | None
    put_call_ratio_oi: float | None
    metrics: tuple[OptionMetric, ...] = ()


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


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    quotes: dict[str, Quote] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def quote_for(self, symbol: str) -> Quote | None:
        return self.quotes.get(symbol)
