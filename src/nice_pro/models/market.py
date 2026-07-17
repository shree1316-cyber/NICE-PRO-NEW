"""Stable data contracts shared across the application."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


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
class MarketSnapshot:
    quotes: dict[str, Quote] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def quote_for(self, symbol: str) -> Quote | None:
        return self.quotes.get(symbol)
