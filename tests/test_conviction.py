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


def test_multi_timeframe_gate_blocks_a_trade_when_five_minute_disagrees() -> None:
    now = datetime.now(timezone.utc)
    call = OptionContract(1, "NFO:NIFTYCE", "NIFTY", date.today() + timedelta(days=7), 25000, OptionType.CALL, 75)
    indicators = IndicatorSnapshot(
        symbol="NSE:NIFTY 50", regime=MarketRegime.TREND_UP, calculated_at=now,
        close=25020, vwap=25000, ema_fast=25015, ema_slow=25005, rsi=62, relative_volume=1.5,
    )
    down = IndicatorSnapshot(
        symbol="NSE:NIFTY 50", regime=MarketRegime.TREND_DOWN, calculated_at=now,
        close=24980, vwap=25000, ema_fast=24985, ema_slow=24995, rsi=38,
    )
    chain = OptionChainSnapshot(
        underlying="NIFTY", calculated_at=now, spot=25020, atm_strike=25000, put_call_ratio_oi=None,
        metrics=(OptionMetric(call, 100, 1000, 0, 18, 0.4),),
    )

    result = ConvictionEngine().evaluate(
        indicators,
        chain,
        {60: indicators, 300: down, 900: indicators, 1800: indicators, 3600: indicators},
    )

    assert result.side is Side.NEUTRAL
    assert result.plan is None
    assert "1m and 5m" in " ".join(result.conflicts)


def test_multi_timeframe_alignment_can_create_a_paper_plan() -> None:
    now = datetime.now(timezone.utc)
    call = OptionContract(1, "NFO:NIFTYCE", "NIFTY", date.today() + timedelta(days=7), 25000, OptionType.CALL, 75)
    put = OptionContract(2, "NFO:NIFTYPE", "NIFTY", date.today() + timedelta(days=7), 25000, OptionType.PUT, 75)
    up = IndicatorSnapshot(
        symbol="NSE:NIFTY 50", regime=MarketRegime.TREND_UP, calculated_at=now,
        close=25020, vwap=25000, ema_fast=25015, ema_slow=25005, rsi=62, relative_volume=1.5,
    )
    chain = OptionChainSnapshot(
        underlying="NIFTY", calculated_at=now, spot=25020, atm_strike=25000, put_call_ratio_oi=1.2,
        metrics=(OptionMetric(call, 100, 1000, 0, 18, 0.4), OptionMetric(put, 90, 1200, 0, 19, -0.3)),
    )

    result = ConvictionEngine(ConvictionConfig(max_loss_per_lot=2_000)).evaluate(
        up, chain, {10: up, 30: up, 60: up, 300: up, 900: up, 1800: up, 3600: up}
    )

    assert result.side is Side.BUY
    assert result.mtf_bullish_score == 100
    assert result.mtf_alignment == "STRONG ALIGNMENT"
    assert result.entry_timing == "ALIGNED"
    assert result.grade is TradeGrade.A_PLUS
    assert result.plan is not None
