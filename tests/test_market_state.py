from nice_pro.engines.market_state import MarketState
from nice_pro.models.market import Quote


def test_market_state_replaces_quote_for_same_symbol() -> None:
    state = MarketState()
    state.update_quote(Quote(256265, "NIFTY 50", 25000.0))
    snapshot = state.update_quote(Quote(256265, "NIFTY 50", 25001.5))

    assert snapshot.quote_for("NIFTY 50").last_price == 25001.5
    assert len(snapshot.quotes) == 1
