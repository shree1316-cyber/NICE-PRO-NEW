"""Read-only end-of-day integrity audit for NICE-PRO.

Run from the repository root with ``python audit_eod.py``.  The audit never
changes the journal and never contacts the broker.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any


REQUIRED_ENRICHED_FIELDS = (
    "pcr_oi",
    "iv_skew",
    "expected_move",
    "atm_bid_ask_spread",
    "atm_book_imbalance",
    "estimated_cvd",
    "otm_continuation",
    "five_minute_close",
    "five_minute_atr",
    "five_minute_rsi",
    "five_minute_relative_volume",
)


def _payload(row: tuple[Any, ...]) -> dict[str, Any]:
    try:
        value = json.loads(row[-1])
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def audit(database: Path) -> dict[str, Any]:
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT id, created_at, record_type, underlying, payload_json "
            "FROM journal_records ORDER BY id"
        ).fetchall()

    decisions = [row for row in rows if row[2] == "DECISION"]
    opens = [row for row in rows if row[2] == "PAPER_OPEN"]
    closes = [row for row in rows if row[2] == "PAPER_CLOSE"]
    decision_payloads = [_payload(row) for row in decisions]
    enriched = [
        item for item in decision_payloads
        if (item.get("live_enriched") or {}).get("contract") == "live_enriched_observation_v1"
    ]
    core = [item for item in decision_payloads if item.get("core_ml_shadow")]

    def complete(item: dict[str, Any]) -> bool:
        features = (item.get("live_enriched") or {}).get("live_features") or {}
        return all(features.get(name) is not None for name in REQUIRED_ENRICHED_FIELDS)

    complete_count = sum(complete(item) for item in enriched)
    fresh_count = sum(
        ((item.get("live_enriched") or {}).get("feature_freshness") or {}).get("fresh_contracts", 0) > 0
        for item in enriched
    )

    close_payloads = [_payload(row) for row in closes]
    close_ids = {item.get("open_id") for item in close_payloads}
    active = [row for row in opens if row[0] not in close_ids]
    outcomes = {name: sum(item.get("outcome") == name for item in close_payloads)
                for name in ("WIN", "LOSS", "TIME_EXIT")}
    resolved = outcomes["WIN"] + outcomes["LOSS"]

    policy_opens = [
        _payload(row) for row in opens
        if (_payload(row).get("policy_id") or _payload(row).get("source"))
    ]
    return {
        "database": str(database),
        "decisions": len(decisions),
        "by_market": {market: sum(row[3] == market for row in decisions)
                       for market in ("NIFTY", "SENSEX")},
        "core_ml": {"records": len(core), "latest_status":
                     (core[-1].get("core_ml_shadow") or {}).get("status") if core else None},
        "live_enriched": {
            "observations": len(enriched),
            "complete": complete_count,
            "complete_pct": round(100 * complete_count / len(enriched), 1) if enriched else 0.0,
            "with_fresh_chain": fresh_count,
            "fresh_pct": round(100 * fresh_count / len(enriched), 1) if enriched else 0.0,
            "latest_status": (enriched[-1].get("live_enriched") or {}).get("status") if enriched else None,
        },
        "308d_paper": {
            "opens": len(opens),
            "closes": len(closes),
            "active": len(active),
            "policy_records": len(policy_opens),
            "outcomes": outcomes,
            "resolved_win_pct": round(100 * outcomes["WIN"] / resolved, 1) if resolved else None,
        },
        "latest_decision": {
            "created_at": decisions[-1][1] if decisions else None,
            "market": decisions[-1][3] if decisions else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a read-only NICE-PRO EOD audit")
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(os.getenv("NICE_JOURNAL_DB", "data/nice_pro_journal.sqlite3")),
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    if not args.database.exists():
        parser.error(f"Journal database not found: {args.database}")
    report = audit(args.database)
    if args.as_json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"EOD AUDIT | {report['database']}")
    print(f"DECISIONS: {report['decisions']} | NIFTY {report['by_market']['NIFTY']} | "
          f"SENSEX {report['by_market']['SENSEX']}")
    print(f"308D PAPER: {report['308d_paper']['opens']} opens / "
          f"{report['308d_paper']['closes']} closes / "
          f"{report['308d_paper']['active']} active | {report['308d_paper']['outcomes']}")
    print(f"CORE ML: {report['core_ml']['records']} records | "
          f"{report['core_ml']['latest_status'] or 'not recorded'}")
    enriched = report["live_enriched"]
    print(f"LIVE-ENRICHED: {enriched['observations']} observations | "
          f"complete {enriched['complete']} ({enriched['complete_pct']}%) | "
          f"fresh chain {enriched['with_fresh_chain']} ({enriched['fresh_pct']}%) | "
          f"{enriched['latest_status'] or 'not recorded'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
