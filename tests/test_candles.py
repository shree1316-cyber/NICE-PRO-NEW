from datetime import datetime, timedelta, timezone

from nice_pro.engines.candles import CandleBuilder
from nice_pro.models.market import Quote


def test_candle_builder_closes_a_ten_second_candle() -> None:
    builder = CandleBuilder(10)
    start = datetime(2026, 7, 18, 3, 0, 1, tzinfo=timezone.utc)
    assert builder.update(Quote(1, "NSE:NIFTY 50", 25000, start, volume=100)) is None
    assert builder.update(Quote(1, "NSE:NIFTY 50", 25004, start + timedelta(seconds=5), volume=125)) is None

    candle = builder.update(Quote(1, "NSE:NIFTY 50", 25002, start + timedelta(seconds=10), volume=140))

    assert candle is not None
    assert (candle.open, candle.high, candle.low, candle.close, candle.volume) == (25000, 25004, 25000, 25004, 25)
