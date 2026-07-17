"""Real-time, tick-derived candles for the scalping and intraday engines."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from nice_pro.models.market import Candle, Quote


@dataclass(slots=True)
class _OpenCandle:
    opened_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class CandleBuilder:
    def __init__(self, timeframe_seconds: int) -> None:
        if timeframe_seconds <= 0:
            raise ValueError("timeframe_seconds must be positive")
        self.timeframe_seconds = timeframe_seconds
        self._open: dict[str, _OpenCandle] = {}
        self._last_cumulative_volume: dict[str, int] = {}

    def update(self, quote: Quote) -> Candle | None:
        opened_at = self._bucket_start(quote.received_at)
        volume_delta = self._volume_delta(quote)
        current = self._open.get(quote.symbol)
        if current is None:
            self._open[quote.symbol] = _OpenCandle(
                opened_at, quote.last_price, quote.last_price, quote.last_price, quote.last_price, volume_delta
            )
            return None
        if current.opened_at != opened_at:
            closed = Candle(
                symbol=quote.symbol,
                timeframe_seconds=self.timeframe_seconds,
                opened_at=current.opened_at,
                closed_at=current.opened_at + timedelta(seconds=self.timeframe_seconds),
                open=current.open,
                high=current.high,
                low=current.low,
                close=current.close,
                volume=current.volume,
            )
            self._open[quote.symbol] = _OpenCandle(
                opened_at, quote.last_price, quote.last_price, quote.last_price, quote.last_price, volume_delta
            )
            return closed
        current.high = max(current.high, quote.last_price)
        current.low = min(current.low, quote.last_price)
        current.close = quote.last_price
        current.volume += volume_delta
        return None

    def _bucket_start(self, timestamp: datetime) -> datetime:
        instant = timestamp.astimezone(timezone.utc)
        seconds = int(instant.timestamp())
        return datetime.fromtimestamp(seconds - seconds % self.timeframe_seconds, tz=timezone.utc)

    def _volume_delta(self, quote: Quote) -> int:
        if quote.volume is None:
            return 0
        previous = self._last_cumulative_volume.get(quote.symbol, quote.volume)
        self._last_cumulative_volume[quote.symbol] = quote.volume
        return max(0, quote.volume - previous)
