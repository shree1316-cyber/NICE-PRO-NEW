from datetime import datetime, timedelta, timezone

from nice_pro.engines.market_data import MarketDataEngine
from nice_pro.engines.market_state import MarketState
from nice_pro.models.market import Quote


def test_market_data_updates_snapshot_and_aggregates_candles() -> None:
    engine = MarketDataEngine(MarketState(), timeframes=(10,))
    opened = datetime(2026, 7, 18, 3, 0, 1, tzinfo=timezone.utc)
    engine.process(Quote(1, "NSE:NIFTY 50", 25000, opened))
    update = engine.process(Quote(1, "NSE:NIFTY 50", 25010, opened + timedelta(seconds=10)))

    assert update.snapshot.quote_for("NSE:NIFTY 50").last_price == 25010
    assert len(update.closed_candles) == 1
