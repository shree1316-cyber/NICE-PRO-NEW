from datetime import date, datetime, timedelta, timezone

from nice_pro.engines.option_hero import OptionHeroEngine
from nice_pro.models.market import OptionChainSnapshot, OptionContract, OptionMetric, OptionType, Side, TradeGrade


def test_full_chain_hero_creates_a_risk_capped_paper_call_plan() -> None:
    now = datetime.now(timezone.utc)
    expiry = date.today() + timedelta(days=7)
    call = OptionContract(1, "NFO:NIFTYCE", "NIFTY", expiry, 25000, OptionType.CALL, 75)
    put = OptionContract(2, "NFO:NIFTYPE", "NIFTY", expiry, 25000, OptionType.PUT, 75)
    chain = OptionChainSnapshot(
        underlying="NIFTY", calculated_at=now, spot=25000, atm_strike=25000,
        put_call_ratio_oi=1.20,
        metrics=(
            OptionMetric(call, 100, 1000, 10, 18, 0.2),
            OptionMetric(put, 90, 1300, 30, 19, -0.1),
        ),
        iv_skew=-1.0,
        expected_move=190,
        atm_bid_ask_spread=1.0,
        atm_book_imbalance=0.2,
        atm_estimated_cvd=50,
        otm_continuation=0.3,
    )

    hero = OptionHeroEngine().evaluate(chain)

    assert hero.side is Side.BUY
    assert hero.grade is TradeGrade.A_PLUS
    assert hero.plan is not None
    assert hero.plan.option_symbol == call.symbol
    assert hero.plan.max_loss_per_lot == 1500
