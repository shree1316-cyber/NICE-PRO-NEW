from datetime import datetime, timezone

from nice_pro.ml.features import build_feature_row, derive_core_ml_side
from nice_pro.models.market import IndicatorSnapshot, MarketRegime, Side


def test_features_are_continuous_and_as_of_snapshot() -> None:
    snapshot = IndicatorSnapshot(
        symbol="NSE:NIFTY 50", regime=MarketRegime.TREND_UP,
        calculated_at=datetime(2026, 1, 5, 5, 0, tzinfo=timezone.utc), timeframe_seconds=300,
        close=100, vwap=98, ema_fast=101, ema_slow=99, rsi=62, atr=2, relative_volume=1.3,
        opening_range_high=101, opening_range_low=97,
    )
    row = build_feature_row(snapshot, Side.BUY, prior_close=99, fifteen_bar_close=95)
    assert row.as_of == snapshot.calculated_at
    assert row.values["ema_spread_atr"] == 1
    assert row.values["regime_trend_up"] == 1
    assert row.values["side_buy"] == 1


def test_core_ml_direction_is_candle_only() -> None:
    snapshot = IndicatorSnapshot(
        symbol="NSE:NIFTY 50", regime=MarketRegime.TREND_DOWN,
        calculated_at=datetime(2026, 1, 5, 5, 0, tzinfo=timezone.utc), timeframe_seconds=300,
        close=98, vwap=100, ema_fast=99, ema_slow=101, rsi=38,
    )
    assert derive_core_ml_side(snapshot) is Side.SELL
    # No rule-engine or option-chain parameter is accepted by this function.
    assert build_feature_row(snapshot).side is Side.SELL
