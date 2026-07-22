from datetime import date, datetime, timedelta, timezone

from nice_pro.engines.scalp import ScalpEngine
from nice_pro.models.market import IndicatorSnapshot, MarketRegime, OptionChainSnapshot, OptionContract, OptionMetric, OptionType, Side


def test_scalp_requires_short_timeframe_and_microstructure_alignment() -> None:
    now = datetime.now(timezone.utc)
    expiry = date.today() + timedelta(days=7)
    call = OptionContract(1, "NFO:NIFTYCE", "NIFTY", expiry, 25000, OptionType.CALL, 75)
    put = OptionContract(2, "NFO:NIFTYPE", "NIFTY", expiry, 25000, OptionType.PUT, 75)
    up_10 = IndicatorSnapshot("NSE:NIFTY 50", MarketRegime.TREND_UP, now, timeframe_seconds=10)
    up_30 = IndicatorSnapshot("NSE:NIFTY 50", MarketRegime.TREND_UP, now, timeframe_seconds=30)
    chain = OptionChainSnapshot(
        underlying="NIFTY", calculated_at=now, spot=25000, atm_strike=25000,
        put_call_ratio_oi=1.0,
        metrics=(OptionMetric(call, 100, 1000, 0, 18, 0.3), OptionMetric(put, 90, 1000, 0, 19, -0.1)),
        expected_move=190, atm_bid_ask_spread=1.0, atm_book_imbalance=0.2,
        atm_estimated_cvd=40, otm_continuation=0.2,
    )

    scalp = ScalpEngine().evaluate(chain, {10: up_10, 30: up_30})

    assert scalp.side is Side.BUY
    assert scalp.score == 100
    assert scalp.plan is not None
    assert scalp.plan.option_symbol == call.symbol


def test_scalp_does_not_issue_a_direction_when_flow_conflicts_with_timing() -> None:
    now = datetime.now(timezone.utc)
    expiry = date.today() + timedelta(days=7)
    call = OptionContract(1, "NFO:NIFTYCE", "NIFTY", expiry, 25000, OptionType.CALL, 75)
    put = OptionContract(2, "NFO:NIFTYPE", "NIFTY", expiry, 25000, OptionType.PUT, 75)
    down_10 = IndicatorSnapshot("NSE:NIFTY 50", MarketRegime.TREND_DOWN, now, timeframe_seconds=10)
    down_30 = IndicatorSnapshot("NSE:NIFTY 50", MarketRegime.TREND_DOWN, now, timeframe_seconds=30)
    chain = OptionChainSnapshot(
        underlying="NIFTY", calculated_at=now, spot=25000, atm_strike=25000,
        put_call_ratio_oi=1.0,
        metrics=(OptionMetric(call, 100, 1000, 0, 18, 0.3), OptionMetric(put, 90, 1000, 0, 19, -0.1)),
        expected_move=190, atm_bid_ask_spread=1.0, atm_book_imbalance=0.2,
        atm_estimated_cvd=40, otm_continuation=0.2,
    )

    scalp = ScalpEngine().evaluate(chain, {10: down_10, 30: down_30})

    assert scalp.raw_side is Side.BUY
    assert scalp.side is Side.NEUTRAL
    assert scalp.plan is None
    assert any("conflicts with 10s/30s timing" in item for item in scalp.conflicts)
