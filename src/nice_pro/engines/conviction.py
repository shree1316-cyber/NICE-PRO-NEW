"""Explainable paper-trading conviction and risk-capped plan engine."""

from dataclasses import dataclass

from nice_pro.models.market import (
    ConvictionSnapshot,
    IndicatorSnapshot,
    MarketRegime,
    OptionChainSnapshot,
    OptionType,
    Side,
    TradeGrade,
    TradePlan,
)


@dataclass(frozen=True, slots=True)
class ConvictionConfig:
    max_loss_per_lot: float = 1_500.0
    stop_loss_fraction: float = 0.20
    target_1_multiple: float = 1.25
    target_2_multiple: float = 1.50


class ConvictionEngine:
    """Scores independent market and options evidence, without profit guarantees."""

    def __init__(self, config: ConvictionConfig | None = None) -> None:
        self._config = config or ConvictionConfig()

    def evaluate(self, indicators: IndicatorSnapshot, chain: OptionChainSnapshot) -> ConvictionSnapshot:
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

        side = _side(bullish, bearish)
        confidence = min(100, abs(bullish - bearish) + min(40, bullish + bearish) // 2)
        grade = _grade(side, bullish, bearish, len(conflicts))
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
