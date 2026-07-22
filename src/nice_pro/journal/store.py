"""SQLite-backed, explainable research records for NICE-PRO.

The journal deliberately stores the state *available at decision time*.  It is
not a hindsight report: later outcome analysis can therefore test which
timeframes, indicator categories and option-chain conditions were present when
a paper plan succeeded or failed.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from nice_pro.models.market import (
    ConvictionSnapshot,
    IndicatorSnapshot,
    OptionChainSnapshot,
    OptionHeroSnapshot,
    ScalpSnapshot,
    TradePlan,
)


@dataclass(frozen=True, slots=True)
class ActivePaperPosition:
    """A durable paper position reconstructed from the local journal."""

    journal_open_id: int
    opened_at: datetime
    plan: TradePlan
    source: str
    policy_id: str | None
    decision_id: int | None


class ResearchJournal:
    """Local durable journal for decision snapshots and simulated outcomes."""

    def __init__(self, database_path: Path) -> None:
        self._path = database_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._create_schema()

    @property
    def path(self) -> Path:
        return self._path

    def capture_decision(
        self,
        conviction: ConvictionSnapshot,
        analyses: Mapping[int, IndicatorSnapshot],
        chain: OptionChainSnapshot,
        hero: OptionHeroSnapshot | None,
        scalp: ScalpSnapshot | None,
    ) -> int:
        """Save every field needed to reconstruct a later paper decision."""
        payload = {
            "conviction": _conviction_payload(conviction),
            "timeframes": {
                str(seconds): _indicator_payload(snapshot)
                for seconds, snapshot in sorted(analyses.items())
            },
            "option_chain": _chain_payload(chain),
            "hero": _hero_payload(hero),
            "scalp": _scalp_payload(scalp),
        }
        return self._insert("DECISION", conviction.underlying, payload)

    def record_paper_open(
        self,
        plan: TradePlan,
        source: str,
        decision_id: int | None,
        policy_id: str | None = None,
    ) -> int:
        """Persist an opening before the paper tracker treats it as active."""
        return self._insert(
            "PAPER_OPEN",
            plan.underlying,
            {
                "source": source,
                "policy_id": policy_id,
                "decision_id": decision_id,
                "plan": _plan_payload(plan),
                "status": "ACTIVE",
            },
        )

    def record_paper_close(
        self,
        open_id: int,
        plan: TradePlan,
        exit_price: float,
        outcome: str,
        exit_reason: str,
        observed_price: float | None = None,
        source: str | None = None,
        policy_id: str | None = None,
    ) -> int:
        """Record a conservative simulated exit and preserve the observed quote.

        ``exit_price`` is the model fill.  It may be capped at Target 1 on a
        winner or at the stop price on a loss so a tick beyond the threshold is
        not silently counted as a better fill than the model promised.
        """
        risk_per_unit = max(plan.entry - plan.stop_loss, 0.000001)
        pnl_per_lot = (exit_price - plan.entry) * plan.lot_size
        r_multiple = (exit_price - plan.entry) / risk_per_unit
        return self._insert(
            "PAPER_CLOSE",
            plan.underlying,
            {
                "open_id": open_id,
                "plan": _plan_payload(plan),
                "exit_price": round(exit_price, 4),
                "observed_price": round(observed_price, 4) if observed_price is not None else None,
                "outcome": outcome,
                "exit_reason": exit_reason,
                "source": source,
                "policy_id": policy_id,
                "pnl_per_lot": round(pnl_per_lot, 2),
                "r_multiple": round(r_multiple, 3),
                "model_note": "Paper-only model fill; no order is sent. Observed price is retained separately.",
            },
        )

    def recent_decisions(self, limit: int = 25) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT id, created_at, underlying, payload_json FROM journal_records "
            "WHERE record_type = 'DECISION' ORDER BY id DESC LIMIT ?",
            (max(1, limit),),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row[3])
            conviction = payload["conviction"]
            result.append(
                {
                    "id": row[0],
                    "created_at": row[1],
                    "created_at_ist": _format_ist(row[1]),
                    "underlying": row[2],
                    "side": conviction["side"],
                    "grade": conviction["grade"],
                    "mtf_score": conviction["mtf_score"],
                    "alignment": conviction["alignment"],
                    "core_bull": conviction["core_bull"],
                    "core_bear": conviction["core_bear"],
                }
            )
        return result

    def active_paper_positions(self, source: str | None = None) -> list[ActivePaperPosition]:
        """Return unmatched paper opens, including positions from a prior restart."""
        opens = self._query(
            "SELECT id, created_at, payload_json FROM journal_records "
            "WHERE record_type = 'PAPER_OPEN' ORDER BY id ASC",
            (),
        )
        closes = self._query(
            "SELECT payload_json FROM journal_records WHERE record_type = 'PAPER_CLOSE'",
            (),
        )
        closed_open_ids = {
            int(payload.get("open_id"))
            for (raw_payload,) in closes
            for payload in (json.loads(raw_payload),)
            if payload.get("open_id") is not None
        }
        positions: list[ActivePaperPosition] = []
        for open_id, created_at, raw_payload in opens:
            if int(open_id) in closed_open_ids:
                continue
            payload = json.loads(raw_payload)
            if source is not None and payload.get("source") != source:
                continue
            plan = _plan_from_payload(payload.get("plan"))
            if plan is None:
                continue
            positions.append(
                ActivePaperPosition(
                    journal_open_id=int(open_id),
                    opened_at=_parse_timestamp(created_at),
                    plan=plan,
                    source=str(payload.get("source", "")),
                    policy_id=payload.get("policy_id"),
                    decision_id=payload.get("decision_id"),
                )
            )
        return positions

    def paper_open_count(self, source: str, underlying: str, session_date: date) -> int:
        """Count policy opens for one underlying in a single IST session."""
        opens = self._query(
            "SELECT created_at, payload_json FROM journal_records "
            "WHERE record_type = 'PAPER_OPEN' AND underlying = ?",
            (underlying,),
        )
        return sum(
            payload.get("source") == source and _parse_timestamp(created_at).astimezone(_IST).date() == session_date
            for created_at, raw_payload in opens
            for payload in (json.loads(raw_payload),)
        )

    def last_paper_close_at(self, source: str, underlying: str) -> datetime | None:
        """Return the most recent closing time for a policy and underlying."""
        rows = self._query(
            "SELECT created_at, payload_json FROM journal_records "
            "WHERE record_type = 'PAPER_CLOSE' AND underlying = ? ORDER BY id DESC",
            (underlying,),
        )
        for created_at, raw_payload in rows:
            if json.loads(raw_payload).get("source") == source:
                return _parse_timestamp(created_at)
        return None

    def performance_summary(
        self, lookback_days: int = 10, source: str | None = None
    ) -> dict[str, Any]:
        """Calculate observed paper outcomes, never a promised win rate."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, lookback_days))
        rows = self._query(
            "SELECT created_at, underlying, payload_json FROM journal_records "
            "WHERE record_type = 'PAPER_CLOSE' ORDER BY id ASC",
            (),
        )
        closed = [
            (created_at, underlying, payload)
            for created_at, underlying, raw_payload in rows
            for payload in (json.loads(raw_payload),)
            if _parse_timestamp(created_at) >= cutoff and (source is None or payload.get("source") == source)
        ]
        wins = [item for item in closed if item[2].get("outcome") == "WIN"]
        losses = [item for item in closed if item[2].get("outcome") == "LOSS"]
        time_exits = [item for item in closed if item[2].get("outcome") == "TIME_EXIT"]
        resolved = wins + losses
        pnl = sum(float(item[2].get("pnl_per_lot", 0)) for item in closed)
        r_values = [float(item[2].get("r_multiple", 0)) for item in closed]
        grouped: dict[str, dict[str, Any]] = {}
        for created_at, underlying, payload in closed:
            stats = grouped.setdefault(
                underlying,
                {"trades": 0, "wins": 0, "losses": 0, "time_exits": 0, "sessions": set()},
            )
            stats["trades"] += 1
            stats["sessions"].add(_parse_timestamp(created_at).astimezone(_IST).date().isoformat())
            if payload.get("outcome") == "WIN":
                stats["wins"] += 1
            elif payload.get("outcome") == "LOSS":
                stats["losses"] += 1
            elif payload.get("outcome") == "TIME_EXIT":
                stats["time_exits"] += 1
        for stats in grouped.values():
            resolved_count = stats["wins"] + stats["losses"]
            stats["win_rate"] = round(100 * stats["wins"] / resolved_count, 1) if resolved_count else None
            stats["observed_sessions"] = len(stats.pop("sessions"))
        observed_sessions = {
            _parse_timestamp(created_at).astimezone(_IST).date().isoformat()
            for created_at, _, _ in closed
        }
        return {
            "lookback_days": lookback_days,
            "source": source,
            "closed_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "time_exits": len(time_exits),
            "resolved_trades": len(resolved),
            "observed_sessions": len(observed_sessions),
            "win_rate": round(100 * len(wins) / len(resolved), 1) if resolved else None,
            "net_pnl_per_lot": round(pnl, 2),
            "average_r": round(sum(r_values) / len(r_values), 3) if r_values else None,
            "by_underlying": grouped,
            "method_note": "Observed paper outcomes only. Win rate excludes time exits; optimise only after an adequate out-of-sample sample.",
        }

    def _create_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS journal_records ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "created_at TEXT NOT NULL, record_type TEXT NOT NULL, "
                "underlying TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_journal_type_time "
                "ON journal_records(record_type, created_at)"
            )

    def _insert(self, record_type: str, underlying: str, payload: dict[str, Any]) -> int:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO journal_records(created_at, record_type, underlying, payload_json) VALUES (?, ?, ?, ?)",
                (created_at, record_type, underlying, json.dumps(payload, separators=(",", ":"))),
            )
            return int(cursor.lastrowid)

    def _query(self, statement: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        with self._lock, self._connect() as connection, closing(connection.cursor()) as cursor:
            cursor.execute(statement, params)
            return cursor.fetchall()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=10, check_same_thread=False)


def _plan_payload(plan: TradePlan | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    return {
        "underlying": plan.underlying, "symbol": plan.option_symbol, "side": plan.side.value, "entry": plan.entry,
        "stop_loss": plan.stop_loss, "target_1": plan.target_1, "target_2": plan.target_2,
        "max_loss_per_lot": plan.max_loss_per_lot, "lot_size": plan.lot_size,
        "note": plan.note,
    }


def _plan_from_payload(payload: dict[str, Any] | None) -> TradePlan | None:
    """Restore a durable plan while remaining compatible with old journals."""
    if not payload:
        return None
    try:
        from nice_pro.models.market import Side

        return TradePlan(
            underlying=str(payload.get("underlying") or _underlying_from_symbol(str(payload["symbol"]))),
            side=Side(str(payload["side"])),
            option_symbol=str(payload["symbol"]),
            entry=float(payload["entry"]),
            stop_loss=float(payload["stop_loss"]),
            target_1=float(payload["target_1"]),
            target_2=float(payload["target_2"]),
            max_loss_per_lot=float(payload["max_loss_per_lot"]),
            lot_size=int(payload["lot_size"]),
            note=str(payload.get("note") or "Paper-trade setup only; no order is submitted."),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _underlying_from_symbol(symbol: str) -> str:
    return "NIFTY" if "NIFTY" in symbol.upper() else "SENSEX"


def _parse_timestamp(value: str) -> datetime:
    """Normalise stored UTC and legacy ISO timestamps into aware UTC values."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _format_ist(value: str) -> str:
    return _parse_timestamp(value).astimezone(_IST).strftime("%Y-%m-%d %I:%M:%S %p IST")


# India has no daylight saving time.  Keeping the offset local also avoids a
# hidden dependency on the IANA timezone database on Windows installations.
_IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def _conviction_payload(item: ConvictionSnapshot) -> dict[str, Any]:
    return {
        "side": item.side.value, "grade": item.grade.value, "core_bull": item.bullish_score,
        "core_bear": item.bearish_score, "confidence": item.confidence,
        "mtf_bull": item.mtf_bullish_score, "mtf_bear": item.mtf_bearish_score,
        "mtf_score": max(item.mtf_bullish_score, item.mtf_bearish_score),
        "alignment": item.mtf_alignment, "entry_timing": item.entry_timing,
        "core_timeframe_seconds": item.core_timeframe_seconds,
        "timeframe_signals": [
            {"timeframe": value.label, "side": value.side.value, "weight": value.weight, "reason": value.reason}
            for value in item.timeframe_signals
        ],
        "bullish_reasons": list(item.bullish_reasons), "bearish_reasons": list(item.bearish_reasons),
        "conflicts": list(item.conflicts), "plan": _plan_payload(item.plan),
    }


def _indicator_payload(item: IndicatorSnapshot) -> dict[str, Any]:
    return {
        "regime": item.regime.value, "close": item.close, "vwap": item.vwap,
        "ema_fast": item.ema_fast, "ema_slow": item.ema_slow, "rsi": item.rsi,
        "atr": item.atr, "relative_volume": item.relative_volume,
        "opening_range_high": item.opening_range_high, "opening_range_low": item.opening_range_low,
        "reasons": list(item.reasons),
        "matrix": [
            {"name": row.name, "category": row.category, "value": row.value, "state": row.state, "reason": row.reason}
            for row in item.readings
        ],
    }


def _chain_payload(item: OptionChainSnapshot) -> dict[str, Any]:
    return {
        "spot": item.spot, "atm_strike": item.atm_strike, "pcr_oi": item.put_call_ratio_oi,
        "max_pain": item.observed_max_pain, "iv_skew": item.iv_skew, "expected_move": item.expected_move,
        "atm_spread": item.atm_bid_ask_spread, "atm_book_imbalance": item.atm_book_imbalance,
        "estimated_cvd": item.atm_estimated_cvd, "otm_continuation": item.otm_continuation,
        "registered_contracts": item.registered_contracts,
        "quoted_contracts": item.quoted_contracts,
        "fresh_contracts": item.fresh_contracts,
        "oldest_quote_age_seconds": item.oldest_quote_age_seconds,
        "atm_quote_age_seconds": item.atm_quote_age_seconds,
        "strikes": [
            {"symbol": metric.contract.symbol, "strike": metric.contract.strike, "type": metric.contract.option_type.value,
             "ltp": metric.last_price, "oi": metric.open_interest, "oi_change": metric.open_interest_change,
             "iv": metric.implied_volatility, "velocity": metric.premium_velocity, "bid": metric.bid, "ask": metric.ask,
              "top_bid_qty": metric.top_bid_quantity, "top_ask_qty": metric.top_ask_quantity,
              "depth_bid_qty": metric.bid_depth_quantity, "depth_ask_qty": metric.ask_depth_quantity,
              "estimated_cvd": metric.estimated_cvd,
              "quote_received_at": metric.quote_received_at.isoformat() if metric.quote_received_at else None}
            for metric in item.metrics
        ],
    }


def _hero_payload(item: OptionHeroSnapshot | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {"side": item.side.value, "bull": item.bullish_score, "bear": item.bearish_score,
            "confidence": item.confidence, "grade": item.grade.value, "reasons": list(item.reasons),
            "conflicts": list(item.conflicts), "plan": _plan_payload(item.plan)}


def _scalp_payload(item: ScalpSnapshot | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {"side": item.side.value, "raw_side": item.raw_side.value, "setup_status": item.setup_status,
            "score": item.score, "confidence": item.confidence,
            "reasons": list(item.reasons), "conflicts": list(item.conflicts), "plan": _plan_payload(item.plan)}
