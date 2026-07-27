"""Decision-time recorder contract for the future Live-Enriched ML model.

This module deliberately *does not* train or score a model.  It creates a
versioned, auditable feature snapshot from the same cached data used by the
dashboard.  A future enriched model may train only after these snapshots can
be joined to closed paper-trade outcomes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from nice_pro.models.market import IndicatorSnapshot, OptionChainSnapshot


LIVE_ENRICHED_CONTRACT = "live_enriched_observation_v1"


def build_live_enriched_observation(
    analyses: Mapping[int, IndicatorSnapshot], chain: OptionChainSnapshot
) -> dict[str, Any]:
    """Return an independent, decision-time feature/provenance envelope.

    The full indicator matrix and individual option contracts remain in the
    parent journal payload.  This envelope makes the live-only fields and
    their freshness explicit for later feature joining and quality filters.
    """
    five_minute = analyses.get(300)
    return {
        "contract": LIVE_ENRICHED_CONTRACT,
        "status": "COLLECTING_ONLY_NOT_TRAINED",
        "underlying": chain.underlying,
        "calculated_at": chain.calculated_at.isoformat(),
        "core_timeframe_seconds": 300,
        "feature_freshness": {
            "registered_contracts": chain.registered_contracts,
            "quoted_contracts": chain.quoted_contracts,
            "fresh_contracts": chain.fresh_contracts,
            "oldest_quote_age_seconds": chain.oldest_quote_age_seconds,
            "atm_quote_age_seconds": chain.atm_quote_age_seconds,
        },
        "live_features": {
            "spot": chain.spot,
            "atm_strike": chain.atm_strike,
            "pcr_oi": chain.put_call_ratio_oi,
            "max_pain": chain.observed_max_pain,
            "iv_skew": chain.iv_skew,
            "expected_move": chain.expected_move,
            "atm_bid_ask_spread": chain.atm_bid_ask_spread,
            "atm_book_imbalance": chain.atm_book_imbalance,
            "estimated_cvd": chain.atm_estimated_cvd,
            "otm_continuation": chain.otm_continuation,
            "five_minute_close": five_minute.close if five_minute else None,
            "five_minute_atr": five_minute.atr if five_minute else None,
            "five_minute_rsi": five_minute.rsi if five_minute else None,
            "five_minute_relative_volume": five_minute.relative_volume if five_minute else None,
            "five_minute_regime": five_minute.regime.value if five_minute else "INSUFFICIENT DATA",
        },
        "source_flags": {
            "option_metrics": "Kite quote/depth snapshots",
            "estimated_cvd": "derived proxy; not exchange tape CVD",
            "otm_continuation": "derived proxy",
            "indicator_matrix": "stored in parent timeframes payload",
            "option_contracts": "stored in parent option_chain payload",
        },
    }
