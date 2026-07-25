"""As-of feature construction for the historical ML-shadow dataset."""

from __future__ import annotations

from datetime import time
from math import cos, pi, sin

from nice_pro.ml.contracts import FeatureRow
from nice_pro.ml.regimes import derive_regime
from nice_pro.engines.indicators import IST
from nice_pro.models.market import IndicatorSnapshot, Side


def build_feature_row(
    snapshot: IndicatorSnapshot,
    side: Side,
    *,
    prior_close: float | None = None,
    fifteen_bar_close: float | None = None,
) -> FeatureRow:
    """Create continuous, bounded features from information known at decision time.

    Option/depth/CVD fields are intentionally excluded here: Kite does not provide
    their historical time series. They can join a later live-journal model only.
    """
    close = snapshot.close or 0.0
    atr = max(snapshot.atr or 0.0, close * 0.0001, 1e-9)
    regime = derive_regime(snapshot)
    local = snapshot.calculated_at.astimezone(IST).time()
    seconds = local.hour * 3600 + local.minute * 60 + local.second
    session_start = time(9, 15)
    start_seconds = session_start.hour * 3600 + session_start.minute * 60
    session_fraction = min(1.0, max(0.0, (seconds - start_seconds) / (6.25 * 3600)))
    values = {
        # Trend
        "ema_spread_atr": ((snapshot.ema_fast or close) - (snapshot.ema_slow or close)) / atr,
        "vwap_distance_atr": (close - (snapshot.vwap or close)) / atr,
        "trend_strength_atr": regime.trend_strength,
        # Momentum
        "rsi_normalized": (snapshot.rsi or 50.0) / 100.0,
        "return_1bar": (close / prior_close - 1.0) if prior_close else 0.0,
        "return_15bar": (close / fifteen_bar_close - 1.0) if fifteen_bar_close else 0.0,
        # Volatility
        "atr_percent": regime.atr_percent,
        # Levels / opening range
        "opening_range_position": _range_position(close, snapshot.opening_range_low, snapshot.opening_range_high),
        # Futures-volume proxy when available; zero represents unknown/non-positive,
        # and availability is recorded separately for later model filtering.
        "relative_volume": snapshot.relative_volume or 0.0,
        "volume_available": float(snapshot.relative_volume is not None),
        # Session clock, giving the model intraday timing without a date identifier.
        "session_fraction": session_fraction,
        "session_sin": sin(2 * pi * session_fraction),
        "session_cos": cos(2 * pi * session_fraction),
        "side_buy": float(side is Side.BUY),
        "side_sell": float(side is Side.SELL),
    }
    values.update(regime.values)
    return FeatureRow(snapshot.calculated_at, snapshot.symbol, side, regime.regime, values)


def _range_position(value: float, low: float | None, high: float | None) -> float:
    if low is None or high is None or high <= low:
        return 0.5
    return min(2.0, max(-1.0, (value - low) / (high - low)))
