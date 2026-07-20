from datetime import date, datetime, timedelta, timezone

from nice_pro.engines.options import OptionChainEngine
from nice_pro.models.market import OptionContract, OptionType, Quote


def test_option_chain_reports_pcr_oi_and_premium_velocity() -> None:
    expiry = date.today() + timedelta(days=7)
    call = OptionContract(10, "NFO:NIFTYCE", "NIFTY", expiry, 25000, OptionType.CALL)
    put = OptionContract(11, "NFO:NIFTYPE", "NIFTY", expiry, 25000, OptionType.PUT)
    engine = OptionChainEngine()
    engine.register([call, put])
    now = datetime.now(timezone.utc)
    engine.update(Quote(10, call.symbol, 150, now, open_interest=1000), spot=25000)
    engine.update(Quote(10, call.symbol, 155, now + timedelta(seconds=5), open_interest=1100), spot=25000)
    chain = engine.update(Quote(11, put.symbol, 140, now + timedelta(seconds=5), open_interest=1500), spot=25000)

    assert chain is not None
    assert chain.atm_strike == 25000
    assert chain.put_call_ratio_oi == 1500 / 1100
    assert chain.observed_strikes == (25000,)
    assert next(metric for metric in chain.metrics if metric.contract.option_type is OptionType.CALL).premium_velocity == 1


def test_option_premium_velocity_handles_mixed_naive_and_aware_timestamps() -> None:
    """Kite can provide a naive IST exchange timestamp after a UTC fallback."""
    expiry = date.today() + timedelta(days=7)
    call = OptionContract(10, "NFO:NIFTYCE", "NIFTY", expiry, 25000, OptionType.CALL)
    engine = OptionChainEngine()
    engine.register([call])
    naive_ist = datetime(2026, 1, 1, 9, 15)
    aware_utc = datetime(2026, 1, 1, 3, 45, 5, tzinfo=timezone.utc)

    engine.update(Quote(10, call.symbol, 150, naive_ist, open_interest=1000), spot=25000)
    chain = engine.update(Quote(10, call.symbol, 155, aware_utc, open_interest=1000), spot=25000)

    assert chain is not None
    metric = next(item for item in chain.metrics if item.contract.option_type is OptionType.CALL)
    assert metric.premium_velocity == 1
