"""Stable data contracts shared across the application."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
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
