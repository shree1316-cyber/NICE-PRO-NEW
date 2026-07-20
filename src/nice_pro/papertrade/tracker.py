"""Conservative paper-plan tracker used to create measurable research outcomes."""

from __future__ import annotations

from dataclasses import dataclass

from nice_pro.journal.store import ResearchJournal
from nice_pro.models.market import ConvictionSnapshot, OptionChainSnapshot, TradePlan


@dataclass(slots=True)
class _ActivePaperTrade:
    journal_open_id: int
    plan: TradePlan


class PaperTradeTracker:
    """Tracks one paper position per underlying, without submitting orders.

    The first version measures a clean, reproducible outcome: either the
    suggested stop is reached or Target 1 is reached. Target 2 and discretionary
    exits remain recorded in the plan but are not silently simulated.
    """

    def __init__(self, journal: ResearchJournal) -> None:
        self._journal = journal
        self._active: dict[str, _ActivePaperTrade] = {}

    def evaluate(self, conviction: ConvictionSnapshot, chain: OptionChainSnapshot, decision_id: int | None) -> None:
        active = self._active.get(conviction.underlying)
        if active is None and conviction.plan is not None:
            open_id = self._journal.record_paper_open(conviction.plan, "MTF_CONVICTION", decision_id)
            self._active[conviction.underlying] = _ActivePaperTrade(open_id, conviction.plan)
            return
        if active is None:
            return
        price = next((metric.last_price for metric in chain.metrics if metric.contract.symbol == active.plan.option_symbol), None)
        if price is None:
            return
        if price <= active.plan.stop_loss:
            self._journal.record_paper_close(active.journal_open_id, active.plan, price, "LOSS", "STOP_LOSS")
            self._active.pop(conviction.underlying, None)
        elif price >= active.plan.target_1:
            self._journal.record_paper_close(active.journal_open_id, active.plan, price, "WIN", "TARGET_1")
            self._active.pop(conviction.underlying, None)

    def active_plan(self, underlying: str) -> TradePlan | None:
        active = self._active.get(underlying)
        return active.plan if active is not None else None
