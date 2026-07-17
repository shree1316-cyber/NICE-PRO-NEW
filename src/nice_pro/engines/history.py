"""Bounded one-minute candle histories used by indicator calculations."""

from collections import defaultdict, deque
from collections.abc import Iterable
from threading import RLock

from nice_pro.models.market import Candle


class CandleHistory:
    def __init__(self, maxlen: int = 600) -> None:
        self._candles: dict[str, deque[Candle]] = defaultdict(lambda: deque(maxlen=maxlen))
        self._lock = RLock()

    def extend(self, candles: Iterable[Candle]) -> None:
        with self._lock:
            for candle in sorted(candles, key=lambda item: item.opened_at):
                self._append(candle)

    def append(self, candle: Candle) -> None:
        with self._lock:
            self._append(candle)

    def _append(self, candle: Candle) -> None:
        series = self._candles[candle.symbol]
        if series and series[-1].opened_at == candle.opened_at:
            series[-1] = candle
        elif not series or candle.opened_at > series[-1].opened_at:
            series.append(candle)

    def for_symbol(self, symbol: str) -> tuple[Candle, ...]:
        with self._lock:
            return tuple(self._candles[symbol])
