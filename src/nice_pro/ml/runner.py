"""Train the research-only ML shadow model from Kite minute history.

Example: ``python -m nice_pro.ml.runner --days 300 --underlying NIFTY``.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from nice_pro.config.settings import Settings, Subscription
from nice_pro.ml.dataset import HistoricalDatasetBuilder
from nice_pro.ml.monitoring import FeatureImportanceTracker
from nice_pro.ml.registry import ModelRegistry
from nice_pro.ml.runtime import MLDependencyError
from nice_pro.ml.trainer import ModelTrainer
from nice_pro.ml.walk_forward import WalkForwardValidator, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="NICE-PRO ML shadow trainer (research only)")
    parser.add_argument("--days", type=int, default=300, help="Calendar lookback, 180 to 365 days")
    parser.add_argument("--from-date", type=_date_arg)
    parser.add_argument("--to-date", type=_date_arg)
    parser.add_argument("--underlying", choices=("NIFTY", "SENSEX"), default="NIFTY")
    parser.add_argument("--output", type=Path, default=Path("data/ml_models"))
    args = parser.parse_args()
    if (args.from_date is None) != (args.to_date is None):
        parser.error("Use --from-date and --to-date together")
    if args.from_date is not None:
        if args.from_date >= args.to_date:
            parser.error("--to-date must be after --from-date")
        start = datetime.combine(args.from_date, time(9, 15), tzinfo=_IST)
        end = datetime.combine(args.to_date, time(15, 30), tzinfo=_IST)
    else:
        if not 180 <= args.days <= 365:
            parser.error("--days must be between 180 and 365")
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=args.days)
    settings = Settings.load()
    subscription = _subscription_for(settings.subscriptions, args.underlying)
    if subscription is None:
        raise SystemExit(f"No configured {args.underlying} subscription.")
    try:
        from nice_pro.services.kite import KiteService

        print("Downloading completed one-minute candles in Kite-safe chunks...")
        candles = KiteService(settings).historical_minute_candles_range(subscription, start, end)
        if not candles:
            raise SystemExit("Kite returned no historical candles.")
        print(f"Building as-of ML samples from {len(candles):,} candles...")
        samples = HistoricalDatasetBuilder().build(candles)
        print(f"Built {len(samples):,} labelled directional samples. Running rolling validation...")
        folds = WalkForwardValidator().validate(samples)
        artifact = ModelTrainer().fit(samples)
        registry = ModelRegistry(args.output)
        model_path, metadata_path = registry.save_shadow(artifact)
        FeatureImportanceTracker(args.output / "importance_history.json").record(artifact)
    except MLDependencyError as error:
        raise SystemExit(str(error)) from error
    report = {
        "mode": "shadow_only",
        "underlying": args.underlying,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "candles": len(candles),
        "samples": len(samples),
        "walk_forward": summary(folds),
        "calibration": {
            "roc_auc": artifact.calibration_metrics.roc_auc,
            "average_precision": artifact.calibration_metrics.average_precision,
            "brier_score": artifact.calibration_metrics.brier_score,
        },
        "model": str(model_path),
        "metadata": str(metadata_path),
        "notice": "ML score is display-only. It does not change the 308D policy or submit orders.",
    }
    report_path = args.output / "latest_shadow_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


_IST = timezone(timedelta(hours=5, minutes=30))


def _date_arg(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected YYYY-MM-DD") from error


def _subscription_for(subscriptions: tuple[Subscription, ...], underlying: str) -> Subscription | None:
    return next((item for item in subscriptions if underlying in item.symbol), None)


if __name__ == "__main__":
    main()
