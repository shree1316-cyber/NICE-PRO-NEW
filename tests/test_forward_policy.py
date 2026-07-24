from dataclasses import replace
from datetime import datetime, time, timezone

from nice_pro.engines.indicators import IST
from nice_pro.journal.store import ResearchJournal
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
from nice_pro.papertrade.tracker import PaperTradeTracker


def _plan() -> TradePlan:
    return TradePlan("NIFTY", Side.BUY, "NIFTYTESTCE", 100, 90, 110, 120, 500, 50)


def _conviction(plan: TradePlan | None = None) -> ConvictionSnapshot:
    return ConvictionSnapshot(
        "NIFTY",
        datetime.now(timezone.utc),
        Side.BUY,
        55,
        10,
        75,
        TradeGrade.A,
        mtf_bullish_score=70,
        mtf_bearish_score=5,
        mtf_alignment="INTRADAY ALIGNED",
        entry_timing="ALIGNED",
        plan=plan,
    )


def _chain(price: float) -> OptionChainSnapshot:
    now = datetime.now(timezone.utc)
    contract = OptionContract(
        1,
        "NIFTYTESTCE",
        "NIFTY",
        datetime.now().date(),
        24_000,
        OptionType.CALL,
        50,
    )
    put_contract = OptionContract(
        2,
        "NIFTYTESTPE",
        "NIFTY",
        datetime.now().date(),
        24_000,
        OptionType.PUT,
        50,
    )
    return OptionChainSnapshot(
        "NIFTY",
        now,
        24_000,
        24_000,
        1.1,
        (
            OptionMetric(contract, price, 100, 5, 12.0, 1.0, quote_received_at=now),
            OptionMetric(put_contract, 100, 100, 5, 12.0, 1.0, quote_received_at=now),
        ),
        registered_contracts=2,
        quoted_contracts=2,
        fresh_contracts=2,
        atm_quote_age_seconds=0.0,
    )


def _policy(*, max_trades_per_day: int = 3, cooldown_minutes: int = 15) -> ForwardTestPolicy:
    return ForwardTestPolicy(
        entry_start=time.min,
        entry_end=time(23, 59),
        force_exit_time=time(23, 59),
        max_trades_per_day=max_trades_per_day,
        cooldown_minutes=cooldown_minutes,
    )


def test_policy_tracker_restores_open_and_uses_target_one_model_fill(tmp_path):
    journal = ResearchJournal(tmp_path / "journal.sqlite3")
    policy = _policy()
    tracker = PaperTradeTracker(journal, policy)

    tracker.evaluate(_conviction(_plan()), _chain(100), decision_id=1)
    assert tracker.active_plan("NIFTY") is not None
    assert len(journal.active_paper_positions(policy.source)) == 1

    restored = PaperTradeTracker(journal, policy)
    assert restored.active_plan("NIFTY") is not None
    restored.evaluate(_conviction(_plan()), _chain(125), decision_id=None)

    report = journal.performance_summary(10, source=policy.source)
    assert report["closed_trades"] == 1
    assert report["wins"] == 1
    assert report["average_r"] == 1.0
    assert report["observed_sessions"] == 1
    assert not journal.active_paper_positions(policy.source)


def test_policy_tracker_requires_fresh_decision_and_respects_cooldown(tmp_path):
    journal = ResearchJournal(tmp_path / "journal.sqlite3")
    policy = _policy(cooldown_minutes=15)
    tracker = PaperTradeTracker(journal, policy)

    tracker.evaluate(_conviction(_plan()), _chain(100), decision_id=1)
    tracker.evaluate(_conviction(_plan()), _chain(111), decision_id=None)
    assert tracker.active_plan("NIFTY") is None

    tracker.evaluate(_conviction(_plan()), _chain(100), decision_id=None)
    assert tracker.active_plan("NIFTY") is None
    tracker.evaluate(_conviction(_plan()), _chain(100), decision_id=2)
    assert tracker.active_plan("NIFTY") is None


def test_policy_tracker_respects_daily_cap(tmp_path):
    journal = ResearchJournal(tmp_path / "journal.sqlite3")
    policy = _policy(max_trades_per_day=1, cooldown_minutes=0)
    tracker = PaperTradeTracker(journal, policy)

    tracker.evaluate(_conviction(_plan()), _chain(100), decision_id=1)
    tracker.evaluate(_conviction(_plan()), _chain(111), decision_id=None)
    tracker.evaluate(_conviction(_plan()), _chain(100), decision_id=2)

    assert tracker.active_plan("NIFTY") is None
    assert journal.paper_open_count(policy.source, "NIFTY", datetime.now(IST).date()) == 1


def test_nifty_candidate_does_not_open_a_sensex_forward_position(tmp_path):
    journal = ResearchJournal(tmp_path / "journal.sqlite3")
    tracker = PaperTradeTracker(journal, _policy())
    sensex_plan = TradePlan("SENSEX", Side.BUY, "SENSEXTESTCE", 100, 90, 110, 120, 500, 20)
    sensex = ConvictionSnapshot(
        "SENSEX",
        datetime.now(timezone.utc),
        Side.BUY,
        55,
        10,
        75,
        TradeGrade.A,
        mtf_bullish_score=70,
        mtf_bearish_score=5,
        mtf_alignment="INTRADAY ALIGNED",
        entry_timing="ALIGNED",
        plan=sensex_plan,
    )
    sensex_contract = OptionContract(2, "SENSEXTESTCE", "SENSEX", datetime.now().date(), 77_000, OptionType.CALL, 20)
    sensex_chain = OptionChainSnapshot(
        "SENSEX", datetime.now(timezone.utc), 77_000, 77_000, 1.1,
        (OptionMetric(sensex_contract, 100, 100, 5, 12.0, 1.0),),
    )

    tracker.evaluate(sensex, sensex_chain, decision_id=1)

    assert tracker.active_plan("SENSEX") is None


def test_policy_blocks_incomplete_chain_before_opening(tmp_path):
    journal = ResearchJournal(tmp_path / "journal.sqlite3")
    tracker = PaperTradeTracker(journal, _policy())
    incomplete = replace(_chain(100), quoted_contracts=1)

    assert not tracker.evaluate(_conviction(_plan()), incomplete, decision_id=1)
    assert tracker.active_plan("NIFTY") is None


def test_scheduled_eod_guard_closes_without_a_new_tick(tmp_path):
    journal = ResearchJournal(tmp_path / "journal.sqlite3")
    policy = _policy()
    policy = replace(policy, force_exit_time=time.min)
    tracker = PaperTradeTracker(journal, policy)
    chain = _chain(100)

    assert tracker.evaluate(_conviction(_plan()), chain, decision_id=1)
    assert tracker.force_exit_due({}, chain.calculated_at) == ("NIFTY",)
    assert tracker.active_plan("NIFTY") is None
    assert journal.performance_summary(10, source=policy.source)["time_exits"] == 1


def test_journal_exposes_ist_timestamp_for_display(tmp_path):
    journal = ResearchJournal(tmp_path / "journal.sqlite3")
    decision = journal.capture_decision(_conviction(), {}, _chain(100), None, None)

    latest = journal.recent_decisions(1)[0]
    assert latest["id"] == decision
    assert latest["created_at_ist"].endswith("IST")
