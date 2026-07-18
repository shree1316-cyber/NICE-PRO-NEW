from datetime import datetime, timedelta, timezone

from nice_pro.engines.indicators import IndicatorEngine
from nice_pro.models.market import Candle, MarketRegime


def test_indicator_engine_identifies_aligned_uptrend() -> None:
    opened = datetime(2026, 7, 18, 3, 45, tzinfo=timezone.utc)
    candles = tuple(
        Candle(
            symbol="NSE:NIFTY 50",
            timeframe_seconds=60,
            opened_at=opened + timedelta(minutes=index),
            closed_at=opened + timedelta(minutes=index + 1),
            open=25000 + index,
            high=25001 + index,
            low=24999 + index,
            close=25000.5 + index,
            volume=100 + index,
        )
        for index in range(25)
    )

    result = IndicatorEngine().evaluate("NSE:NIFTY 50", candles)

    assert result.regime is MarketRegime.TREND_UP
    assert result.vwap is not None
    assert result.rsi is not None and result.rsi > 55
    assert len(result.readings) == 100
    assert {reading.category for reading in result.readings} == {
        "Trend", "Momentum", "Volatility", "Levels", "Volume", "Options & Flow"
    }
