from datetime import datetime, timedelta, timezone

from nice_pro.ml.labels import triple_barrier_label
from nice_pro.models.market import Candle, Side


def _bar(index: int, high: float, low: float, close: float) -> Candle:
    opened = datetime(2026, 1, 5, 4, 0, tzinfo=timezone.utc) + timedelta(minutes=index)
    return Candle("NSE:NIFTY 50", 60, opened, opened + timedelta(minutes=1), 100, high, low, close, 1)


def test_triple_barrier_labels_target_before_stop() -> None:
    candles = (_bar(0, 101, 99, 100), _bar(1, 102, 100, 101), _bar(2, 104, 101, 103))
    label = triple_barrier_label(candles, decision_index=0, side=Side.BUY, atr=2, horizon_bars=2)
    assert label is not None and label.value == 1 and label.result == "TARGET"


def test_triple_barrier_uses_stop_on_same_bar_tie() -> None:
    candles = (_bar(0, 101, 99, 100), _bar(1, 104, 97, 100))
    label = triple_barrier_label(candles, decision_index=0, side=Side.BUY, atr=2, horizon_bars=1)
    assert label is not None and label.value == 0 and label.result == "STOP"
