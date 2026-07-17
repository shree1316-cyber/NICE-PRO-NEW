"""In-memory market state; UI and engines read the same immutable snapshot."""

from dataclasses import replace

from nice_pro.models.market import MarketSnapshot, Quote


class MarketState:
    def __init__(self) -> None:
        self._snapshot = MarketSnapshot()

    @property
    def snapshot(self) -> MarketSnapshot:
        return self._snapshot

    def update_quote(self, quote: Quote) -> MarketSnapshot:
        quotes = dict(self._snapshot.quotes)
        quotes[quote.symbol] = quote
        self._snapshot = replace(self._snapshot, quotes=quotes, updated_at=quote.received_at)
        return self._snapshot
