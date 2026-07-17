"""Routes validated quotes into state and multi-timeframe candle builders."""

from dataclasses import dataclass

from nice_pro.engines.candles import CandleBuilder
from nice_pro.engines.market_state import MarketState
from nice_pro.models.market import Candle, MarketSnapshot, Quote


@dataclass(frozen=True, slots=True)
class MarketUpdate:
    snapshot: MarketSnapshot
    closed_candles: tuple[Candle, ...]


class MarketDataEngine:
    def __init__(self, state: MarketState, timeframes: tuple[int, ...] = (10, 30, 60)) -> None:
        self._state = state
        self._builders = tuple(CandleBuilder(timeframe) for timeframe in timeframes)

    def process(self, quote: Quote) -> MarketUpdate:
        snapshot = self._state.update_quote(quote)
        closed_candles = tuple(candle for builder in self._builders if (candle := builder.update(quote)) is not None)
        return MarketUpdate(snapshot=snapshot, closed_candles=closed_candles)
