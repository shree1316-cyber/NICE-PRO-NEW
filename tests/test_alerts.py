from datetime import date, datetime, time, timezone

from nice_pro.alerts.quality import QualityAlertEngine
from nice_pro.models.market import (
    ConvictionSnapshot,
    OptionChainSnapshot,
    OptionContract,
    OptionMetric,
    OptionType,
    Side,
    TradeGrade,
    TradePlan,
)
from nice_pro.papertrade.policy import ForwardTestPolicy


NOW = datetime(2026, 7, 23, 5, 0, tzinfo=timezone.utc)


def _policy() -> ForwardTestPolicy:
    return ForwardTestPolicy(
        entry_start=time.min,
        entry_end=time(23, 59),
        force_exit_time=time(23, 59),
    )


def _snapshot(underlying: str = "NIFTY") -> ConvictionSnapshot:
    plan = TradePlan(
        underlying,
        Side.BUY,
        f"{underlying}TESTCE",
        100,
        90,
        110,
        120,
        500,
        50,
    )
    return ConvictionSnapshot(
        underlying,
        NOW,
        Side.BUY,
        60,
        10,
        80,
        TradeGrade.A,
        mtf_bullish_score=80,
        mtf_bearish_score=5,
        mtf_alignment="INTRADAY ALIGNED",
        entry_timing="ALIGNED",
        plan=plan,
    )


def _chain(snapshot: ConvictionSnapshot, *, fresh: bool = True) -> OptionChainSnapshot:
    contract = OptionContract(
        1,
        snapshot.plan.option_symbol,
        snapshot.underlying,
        date(2026, 7, 30),
        24_000,
        OptionType.CALL,
        50,
    )
    quote_time = NOW if fresh else NOW.replace(hour=4)
    metric = OptionMetric(
        contract,
        100,
        100,
        10,
        12.0,
        0.4,
        quote_received_at=quote_time,
    )
    put_metric = OptionMetric(
        OptionContract(
            2,
            f"{snapshot.underlying}TESTPE",
            snapshot.underlying,
            date(2026, 7, 30),
            24_000,
            OptionType.PUT,
            50,
        ),
        100,
        100,
        10,
        12.0,
        0.4,
        quote_received_at=quote_time,
    )
    return OptionChainSnapshot(
        snapshot.underlying,
        quote_time,
        24_000,
        24_000,
        1.1,
        (metric, put_metric),
        registered_contracts=2,
        quoted_contracts=2,
        fresh_contracts=2,
        atm_quote_age_seconds=0.0 if fresh else 3_600.0,
    )


def test_alert_requires_opened_fresh_nifty_policy_position() -> None:
    engine = QualityAlertEngine()
    snapshot = _snapshot()

    assert engine.should_alert(
        snapshot,
        policy=_policy(),
        decision_id=7,
        active_decision_id=7,
        chain=_chain(snapshot),
        now=NOW,
    )
    # A repeat from the same live position is suppressed by the cooldown.
    assert not engine.should_alert(
        snapshot,
        policy=_policy(),
        decision_id=7,
        active_decision_id=7,
        chain=_chain(snapshot),
        now=NOW,
    )


def test_alert_denies_unvalidated_market_stale_or_unopened_candidate() -> None:
    engine = QualityAlertEngine()
    policy = _policy()
    nifty = _snapshot()
    sensex = _snapshot("SENSEX")

    # SENSEX is not in the current NIFTY-only forward-test policy.
    assert not engine.should_alert(
        sensex,
        policy=policy,
        decision_id=8,
        active_decision_id=8,
        chain=_chain(sensex),
        now=NOW,
    )
    # A dashboard candidate with no newly opened policy position cannot alert.
    assert not engine.should_alert(
        nifty,
        policy=policy,
        decision_id=9,
        active_decision_id=None,
        chain=_chain(nifty),
        now=NOW,
    )
    # A stale full chain cannot alert even if its decision was opened earlier.
    assert not engine.should_alert(
        nifty,
        policy=policy,
        decision_id=10,
        active_decision_id=10,
        chain=_chain(nifty, fresh=False),
        now=NOW,
    )
