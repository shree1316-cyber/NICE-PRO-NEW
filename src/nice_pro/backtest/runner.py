"""Command-line runner for the Kite-compatible 150/300-day core backtest."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nice_pro.backtest.core import CoreBacktestConfig, CoreBacktester
from nice_pro.config.settings import Settings, Subscription


def main() -> None:
    parser = argparse.ArgumentParser(description="NICE-PRO Kite core directional backtest")
    parser.add_argument("--days", type=int, default=300, help="History length from 30 to 300 days (default: 300)")
    parser.add_argument("--underlying", choices=("NIFTY", "SENSEX"), default="NIFTY")
    parser.add_argument("--optimise", action="store_true", help="Run a small train/test parameter sweep; never changes live settings")
    parser.add_argument("--output", type=Path, default=Path("data/backtests"))
    args = parser.parse_args()
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
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    print(f"Downloading {args.days} days of completed 1-minute {args.underlying} candles in Kite-safe chunks...")
    candles = service.historical_minute_candles_range(subscription, start, end)
    if not candles:
        raise SystemExit("Kite returned no historical candles. Check your access token and instrument token.")
    report = CoreBacktester().run(candles)
    args.output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = args.output / f"{args.underlying.lower()}_core_{args.days}d_{stamp}"
    _write_report(base, report)
    print(json.dumps(report.summary(), indent=2))
    print(f"Saved report: {base}.json and {base}_trades.csv")
    if args.optimise:
        optimisation = _optimise(candles)
        path = base.with_name(base.name + "_optimisation.json")
        path.write_text(json.dumps(optimisation, indent=2), encoding="utf-8")
        print(f"Saved optimisation candidates: {path}")


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


def _optimise(candles) -> list[dict[str, object]]:  # type: ignore[no-untyped-def]
    """Small grid ranked in-sample and independently shown on the final 30%."""
    split = int(len(candles) * 0.70)
    train, test = candles[:split], candles[split:]
    # The core signals are unchanged between parameter candidates. Calculate
    # them once per split, then replay each risk/threshold configuration.
    prepared_train = CoreBacktester().prepare(train)
    prepared_test = CoreBacktester().prepare(test)
    candidates: list[dict[str, object]] = []
    for score in (55, 65, 75):
        for stop in (0.8, 1.0, 1.2):
            for target in (1.0, 1.25, 1.5):
                config = CoreBacktestConfig(minimum_mtf_score=score, stop_atr_multiple=stop, target_one_r=target)
                engine = CoreBacktester(config)
                train_report = engine.run_prepared(train, prepared_train)
                test_report = engine.run_prepared(test, prepared_test)
                candidates.append({
                    "config": {"minimum_mtf_score": score, "stop_atr_multiple": stop, "target_one_r": target},
                    "in_sample_70_percent": train_report.summary(),
                    "out_of_sample_30_percent": test_report.summary(),
                })
    # Rank by average R first; win rate is a secondary diagnostic, not the sole
    # optimisation target.
    return sorted(
        candidates,
        key=lambda item: (
            item["in_sample_70_percent"]["average_r"] or -999,
            item["in_sample_70_percent"]["trades"],
        ),
        reverse=True,
    )


if __name__ == "__main__":
    main()
