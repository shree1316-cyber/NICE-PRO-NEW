"""Conservative triple-barrier labels; labels never feed live inference."""

from __future__ import annotations

from datetime import time

from nice_pro.engines.indicators import IST
from nice_pro.ml.contracts import TripleBarrierLabel
from nice_pro.models.market import Candle, Side


def triple_barrier_label(
    candles: tuple[Candle, ...],
    *,
    decision_index: int,
    side: Side,
    atr: float,
    horizon_bars: int = 90,
    target_r: float = 1.5,
    stop_r: float = 1.0,
) -> TripleBarrierLabel | None:
    """Label the next executable entry. Stop wins same-bar target/stop ties.

    The label stays inside the exchange day and treats a target miss by the
    horizon as zero. This deliberately avoids favourable intrabar hindsight.
    """
    if side is Side.NEUTRAL or decision_index + 1 >= len(candles) or atr <= 0:
        return None
    entry_index = decision_index + 1
    entry_bar = candles[entry_index]
    entry = entry_bar.open
    risk = max(atr * stop_r, entry * 0.0001)
    stop = entry - risk if side is Side.BUY else entry + risk
    target = entry + risk * target_r if side is Side.BUY else entry - risk * target_r
    session = entry_bar.opened_at.astimezone(IST).date()
    final_index = min(len(candles) - 1, entry_index + horizon_bars)
    last = entry_bar
    for index in range(entry_index, final_index + 1):
        bar = candles[index]
        local = bar.opened_at.astimezone(IST)
        if local.date() != session or local.time() >= time(15, 30):
            break
        last = bar
        stop_hit = bar.low <= stop if side is Side.BUY else bar.high >= stop
        target_hit = bar.high >= target if side is Side.BUY else bar.low <= target
        if stop_hit:  # Conservative same-candle precedence.
            return TripleBarrierLabel(0, "STOP", entry, stop, target, bar.closed_at)
        if target_hit:
            return TripleBarrierLabel(1, "TARGET", entry, stop, target, bar.closed_at)
    return TripleBarrierLabel(0, "TIME", entry, stop, target, last.closed_at)
