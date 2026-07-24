from datetime import datetime, timezone

from nice_pro.journal.store import ResearchJournal
from nice_pro.models.market import (
    ConvictionSnapshot, IndicatorSnapshot, MarketRegime, OptionChainSnapshot,
    OptionContract, OptionMetric, OptionType, Side, TradeGrade, TradePlan,
)
from nice_pro.papertrade.tracker import PaperTradeTracker


def _chain(price: float = 100.0) -> OptionChainSnapshot:
    contract = OptionContract(1, "NIFTYTESTCE", "NIFTY", datetime.now().date(), 24_000, OptionType.CALL, 50)
    metric = OptionMetric(contract, price, 100, 5, 12.0, 1.0)
    return OptionChainSnapshot("NIFTY", datetime.now(timezone.utc), 24_000, 24_000, 1.1, (metric,))


def _conviction(plan: TradePlan | None = None) -> ConvictionSnapshot:
    return ConvictionSnapshot(
        "NIFTY", datetime.now(timezone.utc), Side.BUY, 55, 10, 75, TradeGrade.A,
        mtf_bullish_score=70, mtf_bearish_score=5, mtf_alignment="INTRADAY ALIGNED",
        entry_timing="ALIGNED", plan=plan,
    )


def test_journal_preserves_decision_time_inputs(tmp_path):
    journal = ResearchJournal(tmp_path / "journal.sqlite3")
    indicator = IndicatorSnapshot("NSE:NIFTY 50", MarketRegime.TREND_UP, datetime.now(timezone.utc))
    identifier = journal.capture_decision(_conviction(), {300: indicator}, _chain(), None, None)
    decisions = journal.recent_decisions()
    assert identifier > 0
    assert decisions[0]["underlying"] == "NIFTY"
    assert decisions[0]["mtf_score"] == 70


def test_paper_tracker_records_target_one_as_observed_win(tmp_path):
    journal = ResearchJournal(tmp_path / "journal.sqlite3")
    plan = TradePlan("NIFTY", Side.BUY, "NIFTYTESTCE", 100, 90, 110, 120, 500, 50)
    tracker = PaperTradeTracker(journal)
    tracker.evaluate(_conviction(plan), _chain(100), decision_id=1)
    assert tracker.active_plan("NIFTY") is not None
    tracker.evaluate(_conviction(plan), _chain(111), decision_id=None)
    report = journal.performance_summary(10)
    assert report["closed_trades"] == 1
    assert report["wins"] == 1
