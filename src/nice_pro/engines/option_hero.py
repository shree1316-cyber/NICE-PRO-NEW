"""Transparent, paper-only conviction derived from the live full option chain."""

from dataclasses import dataclass

from nice_pro.models.market import (
    OptionChainSnapshot,
    OptionHeroSnapshot,
    OptionMetric,
    OptionType,
    Side,
    TradeGrade,
    TradePlan,
)


@dataclass(frozen=True, slots=True)
class OptionHeroConfig:
    max_loss_per_lot: float = 1_500.0
    stop_loss_fraction: float = 0.20
    target_1_multiple: float = 1.25
    target_2_multiple: float = 1.50


class OptionHeroEngine:
    """Scores chain evidence without mixing in price-action or MTF evidence."""

    def __init__(self, config: OptionHeroConfig | None = None) -> None:
        self._config = config or OptionHeroConfig()

    def evaluate(self, chain: OptionChainSnapshot) -> OptionHeroSnapshot:
        bullish = bearish = 0
        reasons: list[str] = []
        conflicts: list[str] = []
        calls = [item for item in chain.metrics if item.contract.option_type is OptionType.CALL]
        puts = [item for item in chain.metrics if item.contract.option_type is OptionType.PUT]
        call_oi = sum(item.open_interest or 0 for item in calls)
        put_oi = sum(item.open_interest or 0 for item in puts)
        call_delta = sum(item.open_interest_change or 0 for item in calls)
        put_delta = sum(item.open_interest_change or 0 for item in puts)

        pcr = chain.put_call_ratio_oi
        if pcr is not None:
            if pcr >= 1.15:
                bullish += 20
                reasons.append(f"PCR {pcr:.2f} favours put-side OI")
            elif pcr <= 0.85:
                bearish += 20
                reasons.append(f"PCR {pcr:.2f} favours call-side OI")
            else:
                conflicts.append(f"PCR {pcr:.2f} is neutral")
        if call_oi and put_oi:
            if put_oi > call_oi:
                bullish += 7
                reasons.append("Total put OI exceeds call OI")
            elif call_oi > put_oi:
                bearish += 7
                reasons.append("Total call OI exceeds put OI")
        if call_delta or put_delta:
            if put_delta > call_delta:
                bullish += 13
                reasons.append("Session put OI change leads call OI change")
            elif call_delta > put_delta:
                bearish += 13
                reasons.append("Session call OI change leads put OI change")

        skew = chain.iv_skew
        if skew is not None:
            if skew <= -0.5:
                bullish += 12
                reasons.append("ATM call IV exceeds put IV")
            elif skew >= 0.5:
                bearish += 12
                reasons.append("ATM put IV exceeds call IV")
        else:
            conflicts.append("ATM IV skew is not ready")

        if chain.atm_book_imbalance is not None:
            if chain.atm_book_imbalance >= 0.10:
                bullish += 17
                reasons.append("ATM top-5 book is bid-heavy")
            elif chain.atm_book_imbalance <= -0.10:
                bearish += 17
                reasons.append("ATM top-5 book is offer-heavy")
        else:
            conflicts.append("ATM top-5 depth is not ready")

        if chain.atm_estimated_cvd is not None:
            if chain.atm_estimated_cvd > 0:
                bullish += 17
                reasons.append("ATM estimated CVD is positive")
            elif chain.atm_estimated_cvd < 0:
                bearish += 17
                reasons.append("ATM estimated CVD is negative")
        else:
            conflicts.append("Estimated CVD is warming up")

        if chain.otm_continuation is not None:
            if chain.otm_continuation > 0:
                bullish += 14
                reasons.append("First OTM call velocity leads put velocity")
            elif chain.otm_continuation < 0:
                bearish += 14
                reasons.append("First OTM put velocity leads call velocity")
        else:
            conflicts.append("OTM continuation is warming up")

        if chain.expected_move is None:
            conflicts.append("ATM straddle is not ready")
        else:
            reasons.append(f"ATM straddle is {chain.expected_move:.2f} points")
        if chain.atm_bid_ask_spread is None:
            conflicts.append("ATM bid-ask spread is not ready")
        else:
            reasons.append(f"ATM average spread is {chain.atm_bid_ask_spread:.2f}")

        side = _side(bullish, bearish)
        directional = max(bullish, bearish)
        confidence = _confidence(bullish, bearish, len(conflicts))
        grade = _grade(side, directional, len(conflicts))
        plan, rejection = self._plan(chain, side, grade)
        if rejection:
            conflicts.append(rejection)
            if grade is TradeGrade.A_PLUS:
                grade = TradeGrade.A
        return OptionHeroSnapshot(
            underlying=chain.underlying,
            calculated_at=chain.calculated_at,
            side=side,
            bullish_score=bullish,
            bearish_score=bearish,
            confidence=confidence,
            grade=grade,
            reasons=tuple(dict.fromkeys(reasons)),
            conflicts=tuple(dict.fromkeys(conflicts)),
            plan=plan,
        )

    def _plan(
        self, chain: OptionChainSnapshot, side: Side, grade: TradeGrade
    ) -> tuple[TradePlan | None, str | None]:
        if side is Side.NEUTRAL or grade not in {TradeGrade.A, TradeGrade.A_PLUS} or chain.atm_strike is None:
            return None, None
        contract_type = OptionType.CALL if side is Side.BUY else OptionType.PUT
        candidate = next(
            (item for item in chain.metrics if item.contract.strike == chain.atm_strike and item.contract.option_type is contract_type),
            None,
        )
        if candidate is None:
            return None, "ATM option quote is not ready"
        return _risk_capped_plan(candidate, chain.underlying, side, self._config)


def _risk_capped_plan(
    metric: OptionMetric, underlying: str, side: Side, config: OptionHeroConfig
) -> tuple[TradePlan | None, str | None]:
    entry = metric.last_price
    stop_loss = entry * (1 - config.stop_loss_fraction)
    max_loss = (entry - stop_loss) * metric.contract.lot_size
    if max_loss > config.max_loss_per_lot:
        return None, f"Hero plan rejected: loss/lot ₹{max_loss:,.0f} exceeds cap"
    return TradePlan(
        underlying=underlying,
        side=side,
        option_symbol=metric.contract.symbol,
        entry=entry,
        stop_loss=stop_loss,
        target_1=entry * config.target_1_multiple,
        target_2=entry * config.target_2_multiple,
        max_loss_per_lot=max_loss,
        lot_size=metric.contract.lot_size,
        note="Full-chain Hero paper plan only; no order is submitted.",
    ), None


def _side(bullish: int, bearish: int) -> Side:
    if bullish - bearish >= 15:
        return Side.BUY
    if bearish - bullish >= 15:
        return Side.SELL
    return Side.NEUTRAL


def _grade(side: Side, directional: int, conflicts: int) -> TradeGrade:
    """Map the directional evidence budget to an auditable trade grade.

    ``directional`` is the stronger of the bullish and bearish evidence totals,
    on a 0--100 budget.  Missing or unresolved chain inputs cannot turn a weak
    score into an A/A+ grade: they downgrade the two highest grades, while the
    side test continues to prevent a mixed chain from being called directional.
    """
    if side is Side.NEUTRAL:
        return TradeGrade.AVOID
    if directional >= 80 and conflicts <= 1:
        return TradeGrade.A_PLUS
    if directional >= 65 and conflicts <= 2:
        return TradeGrade.A
    if directional >= 45:
        return TradeGrade.B
    if directional >= 25:
        return TradeGrade.C
    return TradeGrade.AVOID


def _confidence(bullish: int, bearish: int, conflicts: int) -> int:
    """Return evidence quality, not a predicted chance of a winning trade.

    The seven directional components form a true 100-point budget. Coverage
    reflects how much live directional evidence is available; dominance reflects
    how strongly one direction outweighs the other. Missing/uncertain fields
    reduce the displayed confidence.
    """
    coverage = min(100, bullish + bearish)
    dominance = abs(bullish - bearish)
    base = round(coverage * 0.60 + dominance * 0.40)
    return max(0, min(100, base - min(20, conflicts * 5)))
