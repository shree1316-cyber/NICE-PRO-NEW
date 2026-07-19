"""Explainable paper-trading conviction and risk-capped plan engine."""

from collections.abc import Mapping
from dataclasses import dataclass

from nice_pro.models.market import (
    ConvictionSnapshot,
    IndicatorSnapshot,
    MarketRegime,
    OptionChainSnapshot,
    OptionType,
    Side,
    TimeframeSignal,
    TradeGrade,
    TradePlan,
)


@dataclass(frozen=True, slots=True)
class ConvictionConfig:
    max_loss_per_lot: float = 1_500.0
    stop_loss_fraction: float = 0.20
    target_1_multiple: float = 1.25
    target_2_multiple: float = 1.50


@dataclass(frozen=True, slots=True)
class _MultiTimeframeAssessment:
    side: Side
    bullish_score: int
    bearish_score: int
    confidence: int
    alignment: str
    entry_timing: str
    signals: tuple[TimeframeSignal, ...]
    conflicts: tuple[str, ...]


class ConvictionEngine:
    """Scores independent market and options evidence, without profit guarantees."""

    def __init__(self, config: ConvictionConfig | None = None) -> None:
        self._config = config or ConvictionConfig()

    def evaluate(
        self,
        indicators: IndicatorSnapshot,
        chain: OptionChainSnapshot,
        analyses_by_timeframe: Mapping[int, IndicatorSnapshot] | None = None,
    ) -> ConvictionSnapshot:
        bullish, bearish = 0, 0
        bull_reasons: list[str] = []
        bear_reasons: list[str] = []
        conflicts: list[str] = []
        if indicators.regime is MarketRegime.TREND_UP:
            bullish += 25
            bull_reasons.extend(indicators.reasons)
        elif indicators.regime is MarketRegime.TREND_DOWN:
            bearish += 25
            bear_reasons.extend(indicators.reasons)
        elif indicators.regime is MarketRegime.VOLATILE:
            conflicts.append("ATR volatility is elevated; option stops may be hit faster")
        elif indicators.regime in {MarketRegime.RANGE, MarketRegime.INSUFFICIENT_DATA}:
            conflicts.append("Trend evidence is not aligned")

        if indicators.close is not None and indicators.vwap is not None:
            if indicators.close > indicators.vwap:
                bullish += 12
                bull_reasons.append("Spot is above session VWAP")
            else:
                bearish += 12
                bear_reasons.append("Spot is below session VWAP")
        if indicators.ema_fast is not None and indicators.ema_slow is not None:
            if indicators.ema_fast > indicators.ema_slow:
                bullish += 10
                bull_reasons.append("EMA 9 is above EMA 21")
            else:
                bearish += 10
                bear_reasons.append("EMA 9 is below EMA 21")
        if indicators.rsi is not None:
            if indicators.rsi >= 55:
                bullish += 8
                bull_reasons.append(f"RSI supports upside ({indicators.rsi:.0f})")
            elif indicators.rsi <= 45:
                bearish += 8
                bear_reasons.append(f"RSI supports downside ({indicators.rsi:.0f})")
        if indicators.relative_volume is not None and indicators.relative_volume >= 1.2:
            if bullish >= bearish:
                bullish += 5
                bull_reasons.append(f"Relative volume is elevated ({indicators.relative_volume:.1f}x)")
            else:
                bearish += 5
                bear_reasons.append(f"Relative volume is elevated ({indicators.relative_volume:.1f}x)")

        pcr = chain.put_call_ratio_oi
        if pcr is not None:
            if pcr >= 1.15:
                bullish += 10
                bull_reasons.append(f"Put-call ratio (OI) is supportive ({pcr:.2f})")
            elif pcr <= 0.85:
                bearish += 10
                bear_reasons.append(f"Put-call ratio (OI) is weak ({pcr:.2f})")
        option_bias = _option_premium_bias(chain)
        if option_bias is Side.BUY:
            bullish += 8
            bull_reasons.append("ATM call premium velocity exceeds put premium velocity")
        elif option_bias is Side.SELL:
            bearish += 8
            bear_reasons.append("ATM put premium velocity exceeds call premium velocity")

        core_side = _side(bullish, bearish)
        confidence = min(100, abs(bullish - bearish) + min(40, bullish + bearish) // 2)
        grade = _grade(core_side, bullish, bearish, len(conflicts))

        # Compatibility mode lets the core engine remain testable in isolation.
        # The running application always supplies the full timeframe map.
        mtf_bull, mtf_bear = bullish, bearish
        alignment, entry_timing = "CORE ONLY", "NOT ASSESSED"
        timeframe_signals: tuple[TimeframeSignal, ...] = ()
        side = core_side
        if analyses_by_timeframe is not None:
            mtf = _evaluate_multi_timeframe(analyses_by_timeframe, core_side)
            mtf_bull, mtf_bear = mtf.bullish_score, mtf.bearish_score
            alignment, entry_timing, timeframe_signals = mtf.alignment, mtf.entry_timing, mtf.signals
            side = mtf.side
            confidence = mtf.confidence
            conflicts.extend(mtf.conflicts)
            if side is not core_side and core_side is not Side.NEUTRAL:
                conflicts.append("5m core evidence does not pass the multi-timeframe trade gate")
            grade = _mtf_grade(side, mtf, core_side, len(conflicts))

        plan, rejection = self._build_plan(side, grade, chain)
        if rejection:
            conflicts.append(rejection)
            grade = TradeGrade.B if grade in {TradeGrade.A, TradeGrade.A_PLUS} else grade
        return ConvictionSnapshot(
            underlying=chain.underlying,
            calculated_at=chain.calculated_at,
            side=side,
            bullish_score=bullish,
            bearish_score=bearish,
            confidence=confidence,
            grade=grade,
            bullish_reasons=tuple(dict.fromkeys(bull_reasons)),
            bearish_reasons=tuple(dict.fromkeys(bear_reasons)),
            conflicts=tuple(dict.fromkeys(conflicts)),
            plan=plan,
            mtf_bullish_score=mtf_bull,
            mtf_bearish_score=mtf_bear,
            mtf_alignment=alignment,
            entry_timing=entry_timing,
            timeframe_signals=timeframe_signals,
            core_timeframe_seconds=300,
        )

    def _build_plan(
        self, side: Side, grade: TradeGrade, chain: OptionChainSnapshot
    ) -> tuple[TradePlan | None, str | None]:
        if side is Side.NEUTRAL or grade not in {TradeGrade.A, TradeGrade.A_PLUS} or chain.atm_strike is None:
            return None, None
        option_type = OptionType.CALL if side is Side.BUY else OptionType.PUT
        candidate = next(
            (
                metric
                for metric in chain.metrics
                if metric.contract.strike == chain.atm_strike and metric.contract.option_type is option_type
            ),
            None,
        )
        if candidate is None:
            return None, "ATM option quote is not available yet"
        entry = candidate.last_price
        stop_loss = entry * (1 - self._config.stop_loss_fraction)
        max_loss = (entry - stop_loss) * candidate.contract.lot_size
        if max_loss > self._config.max_loss_per_lot:
            return None, f"Plan rejected: estimated loss per lot ₹{max_loss:,.0f} exceeds configured limit"
        return (
            TradePlan(
                underlying=chain.underlying,
                side=side,
                option_symbol=candidate.contract.symbol,
                entry=entry,
                stop_loss=stop_loss,
                target_1=entry * self._config.target_1_multiple,
                target_2=entry * self._config.target_2_multiple,
                max_loss_per_lot=max_loss,
                lot_size=candidate.contract.lot_size,
            ),
            None,
        )


def _option_premium_bias(chain: OptionChainSnapshot) -> Side:
    if chain.atm_strike is None:
        return Side.NEUTRAL
    velocities: dict[OptionType, float] = {}
    for metric in chain.metrics:
        if metric.contract.strike == chain.atm_strike and metric.premium_velocity is not None:
            velocities[metric.contract.option_type] = metric.premium_velocity
    call, put = velocities.get(OptionType.CALL), velocities.get(OptionType.PUT)
    if call is not None and put is not None:
        if call > 0 and put < 0:
            return Side.BUY
        if put > 0 and call < 0:
            return Side.SELL
    return Side.NEUTRAL


def _side(bullish: int, bearish: int) -> Side:
    if bullish - bearish >= 10:
        return Side.BUY
    if bearish - bullish >= 10:
        return Side.SELL
    return Side.NEUTRAL


def _grade(side: Side, bullish: int, bearish: int, conflicts: int) -> TradeGrade:
    if side is Side.NEUTRAL:
        return TradeGrade.AVOID
    score = max(bullish, bearish)
    if score >= 65 and conflicts == 0:
        return TradeGrade.A_PLUS
    if score >= 55 and conflicts <= 1:
        return TradeGrade.A
    if score >= 40:
        return TradeGrade.B
    if score >= 25:
        return TradeGrade.C
    return TradeGrade.AVOID


# Timeframes deliberately have category-level weights, rather than adding all
# 100 matrix rows together.  Most technical indicators are correlated; treating
# every row as an independent vote would create false confidence.
_TIMEFRAME_RULES: tuple[tuple[int, str, int], ...] = (
    (10, "10s", 5),
    (30, "30s", 5),
    (60, "1m", 20),
    (300, "5m", 25),
    (900, "15m", 20),
    (1800, "30m", 15),
    (3600, "1h", 10),
)


def _evaluate_multi_timeframe(
    analyses: Mapping[int, IndicatorSnapshot], core_side: Side
) -> _MultiTimeframeAssessment:
    """Apply the explicit multi-timeframe gate used for paper trade plans.

    1m and 5m choose the intraday direction.  15m, 30m and 1h may confirm or
    block it.  10s and 30s are execution timing only and never reverse the
    broader thesis.
    """
    signals: list[TimeframeSignal] = []
    by_timeframe: dict[int, Side] = {}
    bullish = bearish = 0
    for seconds, label, weight in _TIMEFRAME_RULES:
        snapshot = analyses.get(seconds)
        direction, reason = _timeframe_direction(snapshot)
        by_timeframe[seconds] = direction
        signals.append(TimeframeSignal(seconds, label, direction, weight, reason))
        if direction is Side.BUY:
            bullish += weight
        elif direction is Side.SELL:
            bearish += weight

    conflicts: list[str] = []
    one_minute = by_timeframe[60]
    five_minute = by_timeframe[300]
    if one_minute is Side.NEUTRAL or five_minute is Side.NEUTRAL:
        side = Side.NEUTRAL
        conflicts.append("Trade gate waiting: both 1m and 5m need a directional reading")
    elif one_minute is not five_minute:
        side = Side.NEUTRAL
        conflicts.append("Trade blocked: 1m and 5m intraday directions disagree")
    else:
        side = one_minute

    if side is not Side.NEUTRAL:
        opposite_higher = [
            _label_for_timeframe(seconds)
            for seconds in (900, 1800, 3600)
            if by_timeframe[seconds] is not Side.NEUTRAL and by_timeframe[seconds] is not side
        ]
        if opposite_higher:
            conflicts.append(
                "Trade blocked: higher-timeframe bias opposes the setup (" + ", ".join(opposite_higher) + ")"
            )
            side = Side.NEUTRAL

    timing_sides = (by_timeframe[10], by_timeframe[30])
    if side is Side.NEUTRAL:
        timing = "WAITING"
    elif any(timing_side is not Side.NEUTRAL and timing_side is not side for timing_side in timing_sides):
        timing = "CONFLICT"
        conflicts.append("Entry timing conflicts on 10s/30s; wait for a fresh trigger")
    elif all(timing_side is side for timing_side in timing_sides):
        timing = "ALIGNED"
    elif any(timing_side is side for timing_side in timing_sides):
        timing = "PARTIAL"
    else:
        timing = "WARMING UP"

    directional_weight = bullish if side is Side.BUY else bearish if side is Side.SELL else max(bullish, bearish)
    higher_confirmations = sum(1 for seconds in (900, 1800, 3600) if by_timeframe[seconds] is side)
    confidence = min(100, directional_weight + higher_confirmations * 3 + (5 if core_side is side else 0))
    if timing == "CONFLICT":
        confidence = max(0, confidence - 20)
    if side is Side.NEUTRAL:
        confidence = min(confidence, 45)
    alignment = _alignment_label(side, by_timeframe, timing)
    return _MultiTimeframeAssessment(
        side=side,
        bullish_score=bullish,
        bearish_score=bearish,
        confidence=confidence,
        alignment=alignment,
        entry_timing=timing,
        signals=tuple(signals),
        conflicts=tuple(conflicts),
    )


def _timeframe_direction(snapshot: IndicatorSnapshot | None) -> tuple[Side, str]:
    if snapshot is None or snapshot.regime is MarketRegime.INSUFFICIENT_DATA:
        return Side.NEUTRAL, "Waiting for enough candles"
    if snapshot.regime is MarketRegime.TREND_UP:
        return Side.BUY, "Trend up"
    if snapshot.regime is MarketRegime.TREND_DOWN:
        return Side.SELL, "Trend down"
    if snapshot.close is not None and snapshot.vwap is not None and snapshot.ema_fast is not None and snapshot.ema_slow is not None:
        if snapshot.close > snapshot.vwap and snapshot.ema_fast > snapshot.ema_slow and (snapshot.rsi is None or snapshot.rsi >= 55):
            return Side.BUY, "Price/VWAP/EMA aligned up"
        if snapshot.close < snapshot.vwap and snapshot.ema_fast < snapshot.ema_slow and (snapshot.rsi is None or snapshot.rsi <= 45):
            return Side.SELL, "Price/VWAP/EMA aligned down"
    return Side.NEUTRAL, "No directional alignment"


def _alignment_label(side: Side, directions: Mapping[int, Side], timing: str) -> str:
    if side is Side.NEUTRAL:
        return "BLOCKED / WAIT"
    higher = [directions[seconds] for seconds in (900, 1800, 3600)]
    confirmed = sum(item is side for item in higher)
    if confirmed >= 2 and timing == "ALIGNED":
        return "STRONG ALIGNMENT"
    if confirmed >= 1:
        return "INTRADAY ALIGNED"
    return "SHORT-TERM ONLY"


def _label_for_timeframe(seconds: int) -> str:
    return {10: "10s", 30: "30s", 60: "1m", 300: "5m", 900: "15m", 1800: "30m", 3600: "1h"}[seconds]


def _mtf_grade(
    side: Side, assessment: _MultiTimeframeAssessment, core_side: Side, conflicts: int
) -> TradeGrade:
    if side is Side.NEUTRAL:
        return TradeGrade.AVOID
    if assessment.entry_timing == "CONFLICT":
        return TradeGrade.B
    directional = assessment.bullish_score if side is Side.BUY else assessment.bearish_score
    if directional >= 85 and core_side is side and conflicts == 0:
        return TradeGrade.A_PLUS
    if directional >= 65 and core_side is side and conflicts <= 1:
        return TradeGrade.A
    if directional >= 45:
        return TradeGrade.B
    return TradeGrade.C
