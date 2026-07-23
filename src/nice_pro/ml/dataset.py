"""Build a no-look-ahead ML research dataset from Kite minute candles."""

from __future__ import annotations

from bisect import bisect_right

from nice_pro.engines.conviction import ConvictionEngine
from nice_pro.engines.history import _resample
from nice_pro.engines.indicators import IndicatorEngine
from nice_pro.ml.contracts import LabeledSample
from nice_pro.ml.features import build_feature_row
from nice_pro.ml.labels import triple_barrier_label
from nice_pro.models.market import Candle, OptionChainSnapshot, Side

_TIMEFRAMES = (60, 300, 900, 1800, 3600)


class HistoricalDatasetBuilder:
    """Creates one candidate row per completed 5-minute decision point."""

    def __init__(self, horizon_bars: int = 90, target_r: float = 1.5) -> None:
        self._horizon_bars = horizon_bars
        self._target_r = target_r
        self._indicators = IndicatorEngine()
        self._conviction = ConvictionEngine()

    def build(self, minute_candles: tuple[Candle, ...] | list[Candle]) -> tuple[LabeledSample, ...]:
        candles = tuple(sorted(minute_candles, key=lambda bar: bar.opened_at))
        if len(candles) < 500:
            raise ValueError("At least 500 completed minute candles are required for ML research.")
        bars = {60: candles}
        for seconds in _TIMEFRAMES[1:]:
            bars[seconds] = _resample(candles, seconds)
        closed = {seconds: [bar.closed_at for bar in series] for seconds, series in bars.items()}
        output: list[LabeledSample] = []
        for index, decision_bar in enumerate(candles[:-1]):
            if decision_bar.closed_at.minute % 5:
                continue
            analyses = self._analyses_at(decision_bar.closed_at, bars, closed)
            core = analyses[300]
            if core.atr is None or core.atr <= 0:
                continue
            chain = OptionChainSnapshot(decision_bar.symbol, decision_bar.closed_at, core.close, None, None)
            decision = self._conviction.evaluate(core, chain, analyses)
            if decision.side is Side.NEUTRAL:
                continue
            label = triple_barrier_label(
                candles, decision_index=index, side=decision.side, atr=core.atr,
                horizon_bars=self._horizon_bars, target_r=self._target_r,
            )
            if label is None:
                continue
            prior = candles[index - 1].close if index else None
            prior_15 = candles[index - 15].close if index >= 15 else None
            output.append(LabeledSample(build_feature_row(core, decision.side, prior_close=prior, fifteen_bar_close=prior_15), label))
        return tuple(output)

    def _analyses_at(self, as_of, bars, closed):  # type: ignore[no-untyped-def]
        output = {}
        for seconds in _TIMEFRAMES:
            position = bisect_right(closed[seconds], as_of)
            lookback = 500 if seconds == 60 else 150
            history = bars[seconds][max(0, position - lookback):position]
            output[seconds] = self._indicators.evaluate("NSE:NIFTY 50", history, seconds)
        return output
