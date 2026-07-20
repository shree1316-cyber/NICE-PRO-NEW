"""Command-line runner for the Kite-compatible 150/300-day core backtest."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from nice_pro.backtest.core import CoreBacktestConfig, CoreBacktester
from nice_pro.config.settings import Settings, Subscription


def main() -> None:
    parser = argparse.ArgumentParser(description="NICE-PRO Kite core directional backtest")
    parser.add_argument("--days", type=int, help="Rolling history length from 30 to 300 calendar days")
    parser.add_argument("--from-date", type=_date_arg, help="Inclusive start date: YYYY-MM-DD")
    parser.add_argument("--to-date", type=_date_arg, help="Inclusive end date: YYYY-MM-DD")
    parser.add_argument("--underlying", choices=("NIFTY", "SENSEX"), default="NIFTY")
    parser.add_argument(
        "--optimise",
        action="store_true",
        help="Run a quality-ranked 70/30 train/test sweep; never changes live or paper settings",
    )
    parser.add_argument("--output", type=Path, default=Path("data/backtests"))
    args = parser.parse_args()
    using_dates = args.from_date is not None or args.to_date is not None
    if using_dates and (args.from_date is None or args.to_date is None):
        parser.error("--from-date and --to-date must be used together")
    if using_dates and args.days is not None:
        parser.error("Use either --days or --from-date/--to-date, not both")
    if not using_dates:
        args.days = args.days or 300
        if not 30 <= args.days <= 300:
            parser.error("--days must be between 30 and 300")
    settings = Settings.load()
    # Keep CLI help and offline inspection available even before optional
    # Kite dependencies have been installed.
    from nice_pro.services.kite import KiteService

    service = KiteService(settings)
    subscription = _subscription_for(settings.subscriptions, args.underlying)
    if subscription is None:
        raise SystemExit(f"No configured subscription found for {args.underlying}.")
    if using_dates:
        if args.from_date >= args.to_date:
            parser.error("--to-date must be after --from-date")
        start = datetime.combine(args.from_date, time(9, 15), tzinfo=timezone(timedelta(hours=5, minutes=30)))
        end = datetime.combine(args.to_date, time(15, 30), tzinfo=timezone(timedelta(hours=5, minutes=30)))
        period_label = f"{args.from_date.isoformat()} to {args.to_date.isoformat()}"
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=args.days)
        period_label = f"last {args.days} calendar days"
    print(f"Downloading completed 1-minute {args.underlying} candles for {period_label} in Kite-safe chunks...")
    candles = service.historical_minute_candles_range(subscription, start, end)
    if not candles:
        raise SystemExit("Kite returned no historical candles. Check your access token and instrument token.")
    sessions = {candle.opened_at.date() for candle in candles}
    print(f"Received {len(candles):,} candles across {len(sessions)} exchange sessions.")
    report = CoreBacktester().run(candles)
    args.output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    range_name = (
        f"{args.from_date:%Y%m%d}_{args.to_date:%Y%m%d}"
        if using_dates else f"{args.days}d"
    )
    base = args.output / f"{args.underlying.lower()}_core_{range_name}_{stamp}"
    _write_report(base, report)
    print(json.dumps(report.summary(), indent=2))
    print(f"Saved report: {base}.json and {base}_trades.csv")
    if args.optimise:
        optimisation = _optimise(candles)
        path = base.with_name(base.name + "_optimisation.json")
        path.write_text(json.dumps(optimisation, indent=2), encoding="utf-8")
        print(f"Saved optimisation candidates: {path}")


def _date_arg(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected YYYY-MM-DD") from error


def _subscription_for(subscriptions: tuple[Subscription, ...], underlying: str) -> Subscription | None:
    return next((item for item in subscriptions if underlying in item.symbol), None)


def _write_report(base: Path, report) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "model": "Kite Core Directional Backtest",
        "instrument": report.instrument,
        "from": report.from_time.isoformat(), "to": report.to_time.isoformat(),
        "config": {key: str(value) for key, value in asdict(report.config).items()},
        "summary": report.summary(), "excluded_live_only_modules": list(report.excluded_modules),
    }
    base.with_suffix(".json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with base.with_name(base.name + "_trades.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=("signal_time", "entry_time", "exit_time", "side", "entry", "exit", "stop", "target", "r_multiple", "result", "grade", "mtf_score", "alignment"))
        writer.writeheader()
        for trade in report.trades:
            row = asdict(trade)
            row["signal_time"] = trade.signal_time.isoformat()
            row["entry_time"] = trade.entry_time.isoformat()
            row["exit_time"] = trade.exit_time.isoformat()
            row["side"] = trade.side.value
            writer.writerow(row)


def _optimise(candles) -> dict[str, object]:  # type: ignore[no-untyped-def]
    """Evaluate conservative core candidates without changing application settings.

    This is intentionally *not* a win-rate maximiser. A high win rate can be
    obtained by using tiny targets and large losses. Candidates are accepted
    only when both training and untouched testing segments have positive
    average R and a profit factor at or above one.
    """
    split = int(len(candles) * 0.70)
    train, test = candles[:split], candles[split:]
    # The core signals are unchanged between parameter candidates. Calculate
    # them once per split, then replay each risk/threshold configuration.
    prepared_train = CoreBacktester().prepare(train)
    prepared_test = CoreBacktester().prepare(test)
    candidates: list[dict[str, object]] = []
    # A compact grid keeps a 300-day run practical while varying only genuine
    # risk/execution controls. A 65 MTF threshold is the natural A-grade
    # floor; 75 asks for stronger alignment.
    for score in (65, 75):
        for stop in (1.0, 1.2):
            for target in (1.0, 1.25, 1.5):
                for cooldown in (0, 15):
                    for daily_cap in (3, 99):
                        config = CoreBacktestConfig(
                            minimum_mtf_score=score,
                            stop_atr_multiple=stop,
                            target_one_r=target,
                            cooldown_minutes=cooldown,
                            max_trades_per_day=daily_cap,
                        )
                        engine = CoreBacktester(config)
                        train_report = engine.run_prepared(train, prepared_train)
                        test_report = engine.run_prepared(test, prepared_test)
                        in_sample = train_report.summary()
                        out_of_sample = test_report.summary()
                        candidate: dict[str, object] = {
                            "config": {
                                "minimum_mtf_score": score,
                                "minimum_grade": config.minimum_grade.value,
                                "stop_atr_multiple": stop,
                                "target_one_r": target,
                                "cooldown_minutes": cooldown,
                                "max_trades_per_day": daily_cap,
                            },
                            "in_sample_70_percent": in_sample,
                            "out_of_sample_30_percent": out_of_sample,
                        }
                        candidate["robust_for_forward_test"] = _is_robust(in_sample, out_of_sample)
                        candidate["robust_score"] = _robust_score(in_sample, out_of_sample)
                        candidates.append(candidate)

    ranked = sorted(candidates, key=lambda item: float(item["robust_score"]), reverse=True)
    recommended = next((item for item in ranked if item["robust_for_forward_test"]), None)
    return {
        "selection_rule": (
            "Recommended candidates need at least 50 trades in each split, positive average R "
            "and profit factor >= 1.0 in both splits. Ranking uses the weaker split's average R, "
            "then the weaker profit factor; win rate is diagnostic only."
        ),
        "status": "candidate_for_paper_forward_test_only" if recommended else "no_robust_candidate_found",
        "recommended_candidate": recommended,
        "candidates_ranked": ranked,
    }


def _is_robust(in_sample: dict[str, object], out_of_sample: dict[str, object]) -> bool:
    for segment in (in_sample, out_of_sample):
        trades = int(segment.get("trades") or 0)
        average_r = float(segment.get("average_r") or 0.0)
        profit_factor = float(segment.get("profit_factor") or 0.0)
        if trades < 50 or average_r <= 0 or profit_factor < 1.0:
            return False
    return True


def _robust_score(in_sample: dict[str, object], out_of_sample: dict[str, object]) -> float:
    """Rank candidates by their weaker segment, penalising sparse results."""
    average_r = min(float(in_sample.get("average_r") or -9.0), float(out_of_sample.get("average_r") or -9.0))
    profit_factor = min(float(in_sample.get("profit_factor") or 0.0), float(out_of_sample.get("profit_factor") or 0.0))
    sample_size = min(int(in_sample.get("trades") or 0), int(out_of_sample.get("trades") or 0))
    return round(average_r * 100 + (profit_factor - 1.0) * 10 + min(sample_size, 200) / 1_000, 6)


if __name__ == "__main__":
    main()
