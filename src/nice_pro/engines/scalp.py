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
    """Combines 10s/30s direction with live ATM option execution conditions."""

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
        if ten_second is Side.NEUTRAL or thirty_second is Side.NEUTRAL:
            conflicts.append("10s and 30s scalp timing is still warming up")
        elif ten_second is thirty_second:
            if ten_second is Side.BUY:
                bullish += 30
            else:
                bearish += 30
            reasons.append(f"10s and 30s timing align {ten_second.lower()}")
        else:
            conflicts.append("10s and 30s timing disagree")

        # Keep direct calculations explicit rather than treating CVD as exchange truth.
        if chain.atm_estimated_cvd is None:
            conflicts.append("Estimated CVD is warming up")
        elif chain.atm_estimated_cvd > 0:
            bullish += 20
            reasons.append("ATM estimated CVD is positive")
        elif chain.atm_estimated_cvd < 0:
            bearish += 20
            reasons.append("ATM estimated CVD is negative")
        if chain.otm_continuation is None:
            conflicts.append("OTM continuation is warming up")
        elif chain.otm_continuation > 0:
            bullish += 15
            reasons.append("OTM call continuation is positive")
        elif chain.otm_continuation < 0:
            bearish += 15
            reasons.append("OTM put continuation is positive")

        call_velocity, put_velocity = _atm_velocities(chain)
        if call_velocity is None or put_velocity is None:
            conflicts.append("ATM premium velocity is warming up")
        elif call_velocity > put_velocity:
            bullish += 10
            reasons.append("ATM call premium velocity leads")
        elif put_velocity > call_velocity:
            bearish += 10
            reasons.append("ATM put premium velocity leads")

        if chain.atm_bid_ask_spread is None or chain.expected_move is None:
            conflicts.append("ATM spread or straddle is not ready")
        elif chain.atm_bid_ask_spread <= max(1.0, chain.expected_move * 0.02):
            # Execution quality only: no directional vote.
            reasons.append("ATM spread is acceptable for a scalp")
        else:
            conflicts.append("ATM spread is wide for a scalp")

        # Add book imbalance after its directional test without obscuring the
        # simple scoring flow above.
        if chain.atm_book_imbalance is None:
            conflicts.append("ATM top-5 book is not ready")
        elif chain.atm_book_imbalance >= 0.10:
            bullish += 25
            reasons.append("ATM top-5 book is bid-heavy")
        elif chain.atm_book_imbalance <= -0.10:
            bearish += 25
            reasons.append("ATM top-5 book is offer-heavy")

        side = Side.BUY if bullish - bearish >= 20 else Side.SELL if bearish - bullish >= 20 else Side.NEUTRAL
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
