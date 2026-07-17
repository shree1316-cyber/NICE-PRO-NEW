from datetime import date, datetime, timedelta, timezone

from nice_pro.engines.conviction import ConvictionConfig, ConvictionEngine
from nice_pro.models.market import (
    IndicatorSnapshot,
    MarketRegime,
    OptionChainSnapshot,
    OptionContract,
    OptionMetric,
    OptionType,
    Side,
    TradeGrade,
)


def test_aligned_evidence_creates_a_paper_trade_plan() -> None:
    now = datetime.now(timezone.utc)
    call = OptionContract(1, "NFO:NIFTYCE", "NIFTY", date.today() + timedelta(days=7), 25000, OptionType.CALL, 75)
    put = OptionContract(2, "NFO:NIFTYPE", "NIFTY", date.today() + timedelta(days=7), 25000, OptionType.PUT, 75)
    indicators = IndicatorSnapshot(
        symbol="NSE:NIFTY 50", regime=MarketRegime.TREND_UP, calculated_at=now,
        close=25020, vwap=25000, ema_fast=25015, ema_slow=25005, rsi=62,
        relative_volume=1.5, reasons=("Trend is aligned",),
    )
    chain = OptionChainSnapshot(
        underlying="NIFTY", calculated_at=now, spot=25020, atm_strike=25000, put_call_ratio_oi=1.2,
        metrics=(
            OptionMetric(call, 100, 1000, 100, 18, 0.4),
            OptionMetric(put, 90, 1200, 50, 19, -0.3),
        ),
    )

    result = ConvictionEngine(ConvictionConfig(max_loss_per_lot=2_000)).evaluate(indicators, chain)

    assert result.side is Side.BUY
    assert result.grade is TradeGrade.A_PLUS
    assert result.plan is not None
    assert result.plan.max_loss_per_lot == 1500
