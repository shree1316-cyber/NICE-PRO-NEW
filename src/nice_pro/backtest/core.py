"""No-look-ahead historical test for the Kite-backtestable NICE-PRO core.

This deliberately tests only price, volume and multi-timeframe logic that can
be reconstructed from Kite minute candles.  Historical option-chain and order
book components are excluded rather than approximated as real observations.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, time
from statistics import mean

from nice_pro.engines.conviction import ConvictionEngine
from nice_pro.engines.history import _resample
from nice_pro.engines.indicators import IndicatorEngine, IST
from nice_pro.models.market import Candle, OptionChainSnapshot, Side, TradeGrade

_TIMEFRAMES = (60, 300, 900, 1800, 3600)


@dataclass(frozen=True, slots=True)
class CoreBacktestConfig:
    minimum_mtf_score: int = 65
    minimum_grade: TradeGrade = TradeGrade.A
    stop_atr_multiple: float = 1.0
    target_one_r: float = 1.25
    max_holding_minutes: int = 90
    entry_start: time = time(9, 30)
    entry_end: time = time(14, 45)


@dataclass(frozen=True, slots=True)
class HistoricalTrade:
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    side: Side
    entry: float
    exit: float
    stop: float
    target: float
    r_multiple: float
    result: str
    grade: str
    mtf_score: int
    alignment: str


@dataclass(frozen=True, slots=True)
class _SignalEvent:
    index: int
    atr: float
    snapshot: object


@dataclass(frozen=True, slots=True)
class BacktestReport:
    instrument: str
    from_time: datetime
    to_time: datetime
    config: CoreBacktestConfig
    trades: tuple[HistoricalTrade, ...]
    excluded_modules: tuple[str, ...] = (
        "10s and 30s execution timing",
        "historical option-chain Hero inputs",
        "bid/ask depth and book imbalance",
        "estimated CVD and OTM continuation",
        "historical option-premium P/L",
    )

    def summary(self) -> dict[str, float | int | None]:
        wins = [trade for trade in self.trades if trade.result == "WIN"]
        losses = [trade for trade in self.trades if trade.result == "LOSS"]
        r_values = [trade.r_multiple for trade in self.trades]
        gross_win = sum(value for value in r_values if value > 0)
        gross_loss = abs(sum(value for value in r_values if value < 0))
        return {
            "trades": len(self.trades), "wins": len(wins), "losses": len(losses),
            "win_rate": round(100 * len(wins) / len(self.trades), 2) if self.trades else None,
            "average_r": round(mean(r_values), 3) if r_values else None,
            "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else None,
            "max_drawdown_r": round(_max_drawdown(r_values), 3) if r_values else None,
        }


class CoreBacktester:
    """Replays completed 1-minute candles without using future information."""

    def __init__(self, config: CoreBacktestConfig | None = None) -> None:
        self.config = config or CoreBacktestConfig()
        self._indicators = IndicatorEngine()
        self._conviction = ConvictionEngine()

    def run(self, minute_candles: list[Candle] | tuple[Candle, ...]) -> BacktestReport:
        candles = tuple(sorted(minute_candles, key=lambda item: item.opened_at))
        if len(candles) < 500:
            raise ValueError("At least 500 completed one-minute candles are required for a core backtest.")
        return self.run_prepared(candles, self.prepare(candles))

    def prepare(self, minute_candles: list[Candle] | tuple[Candle, ...]) -> tuple[_SignalEvent, ...]:
        """Build eligible historical observations once for a later parameter sweep."""
        candles = tuple(sorted(minute_candles, key=lambda item: item.opened_at))
        if len(candles) < 500:
            raise ValueError("At least 500 completed one-minute candles are required for a core backtest.")
        by_timeframe = {60: candles}
        for seconds in _TIMEFRAMES[1:]:
            by_timeframe[seconds] = _resample(candles, seconds)
        opened = {seconds: [bar.closed_at for bar in bars] for seconds, bars in by_timeframe.items()}
        events: list[_SignalEvent] = []
        # Signals are assessed only at a completed 5-minute bar. The next
        # minute's open is the earliest executable price in this model.
        for index in range(len(candles) - 1):
            signal_bar = candles[index]
            local_time = signal_bar.closed_at.astimezone(IST).time()
            if signal_bar.closed_at.minute % 5 or not (self.config.entry_start <= local_time <= self.config.entry_end):
                continue
            analyses = self._analyses_at(signal_bar.closed_at, by_timeframe, opened)
            core = analyses.get(300)
            if core is None or core.atr is None or core.atr <= 0:
                continue
            # An empty chain intentionally prevents any option-chain vote.
            # The resulting snapshot is solely the candle-reconstructable MTF core.
            chain = OptionChainSnapshot("NIFTY", signal_bar.closed_at, core.close, None, None)
            snapshot = self._conviction.evaluate(core, chain, analyses)
            events.append(_SignalEvent(index, core.atr, snapshot))
        return tuple(events)

    def run_prepared(self, minute_candles: list[Candle] | tuple[Candle, ...], events: tuple[_SignalEvent, ...]) -> BacktestReport:
        candles = tuple(sorted(minute_candles, key=lambda item: item.opened_at))
        trades: list[HistoricalTrade] = []
        blocked_until = -1
        for event in events:
            snapshot = event.snapshot
            direction_score = max(snapshot.mtf_bullish_score, snapshot.mtf_bearish_score)
            if event.index <= blocked_until or not self._eligible(snapshot.side, snapshot.grade, direction_score):
                continue
            trade, blocked_until = self._simulate(candles, event.index + 1, snapshot.side, event.atr, snapshot)
        return BacktestReport(candles[0].symbol, candles[0].opened_at, candles[-1].closed_at, self.config, tuple(trades))

    def _analyses_at(
        self, as_of: datetime, bars: dict[int, tuple[Candle, ...]], closed: dict[int, list[datetime]]
    ) -> dict[int, object]:
        output = {}
        for seconds in _TIMEFRAMES:
            position = bisect_right(closed[seconds], as_of)
            # Session VWAP requires the current session; 500 one-minute bars
            # retains it while keeping the long replay computationally bounded.
            lookback = 500 if seconds == 60 else 150
            history = bars[seconds][max(0, position - lookback) : position]
            output[seconds] = self._indicators.evaluate("NSE:NIFTY 50", history, seconds)
        return output

    def _eligible(self, side: Side, grade: TradeGrade, score: int) -> bool:
        allowed = {TradeGrade.A_PLUS, TradeGrade.A} if self.config.minimum_grade is TradeGrade.A else {TradeGrade.A_PLUS}
        return side is not Side.NEUTRAL and grade in allowed and score >= self.config.minimum_mtf_score

    def _simulate(self, candles: tuple[Candle, ...], entry_index: int, side: Side, atr: float, snapshot) -> tuple[HistoricalTrade, int]:
        entry_bar = candles[entry_index]
        entry = entry_bar.open
        risk = max(atr * self.config.stop_atr_multiple, entry * 0.0001)
        stop = entry - risk if side is Side.BUY else entry + risk
        target = entry + risk * self.config.target_one_r if side is Side.BUY else entry - risk * self.config.target_one_r
        max_index = min(len(candles) - 1, entry_index + self.config.max_holding_minutes)
        entry_session = entry_bar.opened_at.astimezone(IST).date()
        # Intraday positions never cross the exchange session boundary.  A
        # missing after-hours bar must not turn a 90-minute trade into an
        # accidental next-day position.
        while max_index > entry_index and (
            candles[max_index].opened_at.astimezone(IST).date() != entry_session
            or candles[max_index].opened_at.astimezone(IST).time() >= time(15, 30)
        ):
            max_index -= 1
        exit_bar = candles[max_index]
        exit_price, result = exit_bar.close, "TIME_EXIT"
        for position in range(entry_index, max_index + 1):
            bar = candles[position]
            # When a single historical bar touches both levels, use the stop:
            # this conservative rule prevents favourable intrabar hindsight.
            hit_stop = bar.low <= stop if side is Side.BUY else bar.high >= stop
            hit_target = bar.high >= target if side is Side.BUY else bar.low <= target
            if hit_stop:
                exit_bar, exit_price, result = bar, stop, "LOSS"
                max_index = position
                break
            if hit_target:
                exit_bar, exit_price, result = bar, target, "WIN"
                max_index = position
                break
        r_multiple = ((exit_price - entry) / risk) if side is Side.BUY else ((entry - exit_price) / risk)
        return HistoricalTrade(
            signal_time=candles[entry_index - 1].closed_at, entry_time=entry_bar.opened_at,
            exit_time=exit_bar.closed_at, side=side, entry=entry, exit=exit_price,
            stop=stop, target=target, r_multiple=round(r_multiple, 4), result=result,
            grade=snapshot.grade.value, mtf_score=max(snapshot.mtf_bullish_score, snapshot.mtf_bearish_score),
            alignment=snapshot.mtf_alignment,
        ), max_index


def _max_drawdown(values: list[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = min(drawdown, equity - peak)
    return abs(drawdown)
