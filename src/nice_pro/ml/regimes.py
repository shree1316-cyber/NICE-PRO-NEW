"""Deterministic market-regime features used before optional clustering."""

from dataclasses import dataclass

from nice_pro.models.market import IndicatorSnapshot, MarketRegime


@dataclass(frozen=True, slots=True)
class RegimeFeatures:
    regime: MarketRegime
    trend_strength: float
    atr_percent: float
    values: dict[str, float]


def derive_regime(snapshot: IndicatorSnapshot) -> RegimeFeatures:
    """Return transparent one-hot regime features from completed candles only."""
    close = snapshot.close or 0.0
    atr = snapshot.atr or 0.0
    trend_strength = abs((snapshot.ema_fast or close) - (snapshot.ema_slow or close)) / max(atr, close * 0.0001, 1e-9)
    atr_percent = atr / close if close else 0.0
    regime = snapshot.regime
    return RegimeFeatures(
        regime=regime,
        trend_strength=trend_strength,
        atr_percent=atr_percent,
        values={
            "regime_trend_up": float(regime is MarketRegime.TREND_UP),
            "regime_trend_down": float(regime is MarketRegime.TREND_DOWN),
            "regime_range": float(regime is MarketRegime.RANGE),
            "regime_volatile": float(regime is MarketRegime.VOLATILE),
            "trend_strength_atr": trend_strength,
            "atr_percent": atr_percent,
        },
    )
