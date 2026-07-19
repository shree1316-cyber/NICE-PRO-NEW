"""Bounded candle histories, including derived higher-timeframe bars."""

from collections import defaultdict, deque
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from threading import RLock

from nice_pro.models.market import Candle


class CandleHistory:
    """Stores actual bars and derives 5m–1h history from one-minute bars.

    Ten- and thirty-second history begins after NICE-PRO starts because Kite's
    historical endpoint supplies minute and above intervals, not tick replay.
    """

    def __init__(self, maxlen: int = 4_000) -> None:
        self._candles: dict[tuple[str, int], deque[Candle]] = defaultdict(lambda: deque(maxlen=maxlen))
        self._lock = RLock()

    def extend(self, candles: Iterable[Candle]) -> None:
        with self._lock:
            for candle in sorted(candles, key=lambda item: item.opened_at):
                self._append(candle)

    def append(self, candle: Candle) -> None:
        with self._lock:
            self._append(candle)

    def _append(self, candle: Candle) -> None:
        series = self._candles[(candle.symbol, candle.timeframe_seconds)]
        if series and series[-1].opened_at == candle.opened_at:
            series[-1] = candle
        elif not series or candle.opened_at > series[-1].opened_at:
            series.append(candle)

    def for_symbol(self, symbol: str, timeframe_seconds: int = 60) -> tuple[Candle, ...]:
        with self._lock:
            direct = tuple(self._candles[(symbol, timeframe_seconds)])
            if timeframe_seconds <= 60:
                return direct
            derived = _resample(tuple(self._candles[(symbol, 60)]), timeframe_seconds)
            return _merge(derived, direct)


def _merge(primary: tuple[Candle, ...], replacement: tuple[Candle, ...]) -> tuple[Candle, ...]:
    """Prefer actual real-time bars over derived historical bars at same time."""
    merged = {candle.opened_at: candle for candle in primary}
    merged.update({candle.opened_at: candle for candle in replacement})
    return tuple(merged[key] for key in sorted(merged))


def _resample(candles: tuple[Candle, ...], timeframe_seconds: int) -> tuple[Candle, ...]:
    if not candles or timeframe_seconds % 60:
        return ()
    buckets: dict[datetime, list[Candle]] = {}
    for candle in candles:
        opened = _bucket(candle.opened_at, timeframe_seconds)
        buckets.setdefault(opened, []).append(candle)
    output: list[Candle] = []
    for opened, bars in sorted(buckets.items()):
        # Do not make a completed historical bar from a partial bucket.
        if len(bars) < timeframe_seconds // 60:
            continue
        output.append(
            Candle(
                symbol=bars[0].symbol,
                timeframe_seconds=timeframe_seconds,
                opened_at=opened,
                closed_at=opened + timedelta(seconds=timeframe_seconds),
                open=bars[0].open,
                high=max(bar.high for bar in bars),
                low=min(bar.low for bar in bars),
                close=bars[-1].close,
                volume=sum(bar.volume for bar in bars),
            )
        )
    return tuple(output)


def _bucket(timestamp: datetime, timeframe_seconds: int) -> datetime:
    instant = timestamp.astimezone(timezone.utc)
    seconds = int(instant.timestamp())
    return datetime.fromtimestamp(seconds - seconds % timeframe_seconds, tz=timezone.utc)
