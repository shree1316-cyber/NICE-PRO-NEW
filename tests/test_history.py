from datetime import datetime, timedelta, timezone

from nice_pro.engines.history import CandleHistory
from nice_pro.models.market import Candle


def test_history_derives_complete_five_minute_candles_from_one_minute_history() -> None:
    opened = datetime(2026, 7, 18, 3, 45, tzinfo=timezone.utc)
    minutes = [
        Candle(
            symbol="NSE:NIFTY 50",
            timeframe_seconds=60,
            opened_at=opened + timedelta(minutes=index),
            closed_at=opened + timedelta(minutes=index + 1),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            volume=10,
        )
        for index in range(10)
    ]
    history = CandleHistory()
    history.extend(minutes)

    bars = history.for_symbol("NSE:NIFTY 50", 300)

    assert len(bars) == 2
    assert bars[0].open == 100
    assert bars[0].close == 105
    assert bars[0].high == 106
    assert bars[0].low == 99
    assert bars[0].volume == 50
