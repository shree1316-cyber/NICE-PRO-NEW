"""In-memory market state; UI and engines read the same immutable snapshot."""

from dataclasses import replace
from threading import RLock

from nice_pro.models.market import MarketSnapshot, Quote


class MarketState:
    def __init__(self) -> None:
        self._snapshot = MarketSnapshot()
        self._lock = RLock()

    @property
    def snapshot(self) -> MarketSnapshot:
        with self._lock:
            return self._snapshot

    def update_quote(self, quote: Quote) -> MarketSnapshot:
        with self._lock:
            quotes = dict(self._snapshot.quotes)
            quotes[quote.symbol] = quote
            self._snapshot = replace(self._snapshot, quotes=quotes, updated_at=quote.received_at)
            return self._snapshot
