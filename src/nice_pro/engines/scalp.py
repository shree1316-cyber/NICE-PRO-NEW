"""Conservative, short-horizon option scalp assessment for paper trading only."""

from collections.abc import Mapping
from dataclasses import dataclass

from nice_pro.models.market import (
    IndicatorSnapshot,
    MarketRegime,
    OptionChainSnapshot,
    OptionType,
    ScalpSnapshot,
    Side,
    TradePlan,
)


@dataclass(frozen=True, slots=True)
class ScalpConfig:
    max_loss_per_lot: float = 900.0
    stop_loss_fraction: float = 0.08
    target_1_multiple: float = 1.08
    target_2_multiple: float = 1.15


class ScalpEngine:
    """Conservative short-horizon evidence with timing as the safety gate.

    The score is a raw directional-evidence score, not a probability.  The
    visible ``side`` becomes neutral whenever option-flow evidence contradicts
    the aligned 10s/30s timing; this prevents a headline such as ``BUY CE``
    while timing is explicitly selling.
    """

    def __init__(self, config: ScalpConfig | None = None) -> None:
        self._config = config or ScalpConfig()

    def evaluate(
        self, chain: OptionChainSnapshot, analyses: Mapping[int, IndicatorSnapshot]
    ) -> ScalpSnapshot:
        ten_second = _direction(analyses.get(10))
        thirty_second = _direction(analyses.get(30))
        reasons: list[str] = []
        conflicts: list[str] = []
        bullish = bearish = 0
        # Keep short-timeframe timing separate from option-flow direction so
        # the UI can explain a genuine conflict rather than silently folding
        # both into a neutral aggregate score.
        flow_bullish = flow_bearish = 0
        timing_side = Side.NEUTRAL
        if ten_second is Side.NEUTRAL or thirty_second is Side.NEUTRAL:
            conflicts.append("10s and 30s scalp timing is still warming up")
        elif ten_second is thirty_second:
            timing_side = ten_second
            if ten_second is Side.BUY:
                bullish += 40
            else:
                bearish += 40
            reasons.append(f"10s and 30s timing align {ten_second.lower()}")
        else:
            conflicts.append("10s and 30s timing disagree")

        # Keep direct calculations explicit rather than treating CVD as exchange truth.
        if chain.atm_estimated_cvd is None:
            conflicts.append("Estimated CVD is warming up")
        elif chain.atm_estimated_cvd > 0:
            bullish += 25
            flow_bullish += 25
            reasons.append("ATM estimated CVD is positive")
        elif chain.atm_estimated_cvd < 0:
            bearish += 25
            flow_bearish += 25
            reasons.append("ATM estimated CVD is negative")
        if chain.otm_continuation is None:
            conflicts.append("OTM continuation is warming up")
        elif chain.otm_continuation > 0:
            bullish += 20
            flow_bullish += 20
            reasons.append("OTM call continuation is positive")
        elif chain.otm_continuation < 0:
            bearish += 20
            flow_bearish += 20
            reasons.append("OTM put continuation is positive")

        call_velocity, put_velocity = _atm_velocities(chain)
        if call_velocity is None or put_velocity is None:
            conflicts.append("ATM premium velocity is warming up")
        elif call_velocity > put_velocity:
            bullish += 15
            flow_bullish += 15
            reasons.append("ATM call premium velocity leads")
        elif put_velocity > call_velocity:
            bearish += 15
            flow_bearish += 15
            reasons.append("ATM put premium velocity leads")

        if chain.atm_bid_ask_spread is None or chain.expected_move is None:
            conflicts.append("ATM spread or straddle is not ready")
        elif chain.atm_bid_ask_spread <= max(1.0, chain.expected_move * 0.02):
            # Execution quality only: no directional vote.
            reasons.append("ATM spread is acceptable for a scalp")
        else:
            conflicts.append("ATM spread is wide for a scalp")

        # Kite depth supplies available top-five liquidity, but combined
        # CE/PE book imbalance is not a valid directional order-flow signal.
        # It remains an execution-quality gate only.
        if chain.atm_book_imbalance is None:
            conflicts.append("ATM top-5 book is not ready")
        else:
            reasons.append("ATM top-5 depth is available (liquidity check only)")

        if chain.atm_quote_age_seconds is not None and chain.atm_quote_age_seconds > 10:
            conflicts.append(f"ATM quote is stale ({chain.atm_quote_age_seconds:.1f}s)")

        raw_side = (
            Side.BUY
            if flow_bullish - flow_bearish >= 25
            else Side.SELL
            if flow_bearish - flow_bullish >= 25
            else Side.NEUTRAL
        )
        side = raw_side
        if timing_side is Side.NEUTRAL:
            side = Side.NEUTRAL
        elif raw_side is Side.NEUTRAL:
            conflicts.append("Option-flow evidence does not confirm scalp timing")
            side = Side.NEUTRAL
        elif raw_side is not timing_side:
            conflicts.append("Option-flow bias conflicts with 10s/30s timing")
            side = Side.NEUTRAL
        score = max(bullish, bearish)
        confidence = max(0, min(100, score - min(30, len(conflicts) * 7)))
        plan = self._plan(chain, side, score, confidence, conflicts)
        return ScalpSnapshot(
            underlying=chain.underlying,
            calculated_at=chain.calculated_at,
            side=side,
            score=score,
            confidence=confidence,
            reasons=tuple(dict.fromkeys(reasons)),
            conflicts=tuple(dict.fromkeys(conflicts)),
            plan=plan,
            raw_side=raw_side,
            setup_status="PAPER SETUP ELIGIBLE" if plan is not None else "BLOCKED / WAIT",
        )

    def _plan(self, chain: OptionChainSnapshot, side: Side, score: int, confidence: int, conflicts: list[str]) -> TradePlan | None:
        if side is Side.NEUTRAL or score < 70 or confidence < 65 or conflicts or chain.atm_strike is None:
            return None
        option_type = OptionType.CALL if side is Side.BUY else OptionType.PUT
        metric = next((item for item in chain.metrics if item.contract.strike == chain.atm_strike and item.contract.option_type is option_type), None)
        if metric is None:
            return None
        entry = metric.last_price
        stop_loss = entry * (1 - self._config.stop_loss_fraction)
        max_loss = (entry - stop_loss) * metric.contract.lot_size
        if max_loss > self._config.max_loss_per_lot:
            return None
        return TradePlan(
            underlying=chain.underlying,
            side=side,
            option_symbol=metric.contract.symbol,
            entry=entry,
            stop_loss=stop_loss,
            target_1=entry * self._config.target_1_multiple,
            target_2=entry * self._config.target_2_multiple,
            max_loss_per_lot=max_loss,
            lot_size=metric.contract.lot_size,
            note="Scalp paper plan only; no order is submitted.",
        )


def _direction(snapshot: IndicatorSnapshot | None) -> Side:
    if snapshot is None:
        return Side.NEUTRAL
    if snapshot.regime is MarketRegime.TREND_UP:
        return Side.BUY
    if snapshot.regime is MarketRegime.TREND_DOWN:
        return Side.SELL
    return Side.NEUTRAL


def _atm_velocities(chain: OptionChainSnapshot) -> tuple[float | None, float | None]:
    values = {item.contract.option_type: item.premium_velocity for item in chain.metrics if item.contract.strike == chain.atm_strike}
    return values.get(OptionType.CALL), values.get(OptionType.PUT)
