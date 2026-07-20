from datetime import datetime, timedelta, timezone

from nice_pro.backtest.core import CoreBacktester
from nice_pro.models.market import Candle


def test_core_backtester_runs_without_lookahead_on_minute_candles():
    start = datetime(2026, 1, 5, 3, 45, tzinfo=timezone.utc)
    candles = []
    for index in range(2_000):
        price = 24_000 + index * 0.5
        opened = start + timedelta(minutes=index)
        candles.append(Candle("NSE:NIFTY 50", 60, opened, opened + timedelta(minutes=1), price, price + 2, price - 1, price + 0.5, 1_000 + index))
    report = CoreBacktester().run(candles)
    assert report.instrument == "NSE:NIFTY 50"
    assert report.summary()["trades"] > 0
    assert "historical option-chain Hero inputs" in report.excluded_modules
