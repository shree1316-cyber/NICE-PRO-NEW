"""Regularised LightGBM training for research-only ML shadow scores."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from nice_pro.ml.contracts import LabeledSample
from nice_pro.ml.runtime import require_ml


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    max_depth: int = 4
    learning_rate: float = 0.03
    n_estimators: int = 600
    min_child_samples: int = 40
    reg_alpha: float = 0.3
    reg_lambda: float = 1.2
    early_stopping_rounds: int = 50
    random_state: int = 73


@dataclass(frozen=True, slots=True)
class TrainingMetrics:
    samples: int
    positive_rate: float
    roc_auc: float | None
    average_precision: float | None
    brier_score: float | None


@dataclass(slots=True)
class ModelArtifact:
    """A serialisable, versioned model used only by the later shadow display."""

    model: object
    calibrator: object | None
    feature_names: tuple[str, ...]
    feature_importance: dict[str, float]
    trained_at: datetime
    trained_until: datetime
    config: TrainingConfig
    calibration_metrics: TrainingMetrics

    def predict_probability(self, values: dict[str, float]) -> float:
        _, np, *_ = require_ml()
        row = np.array([[float(values.get(name, 0.0)) for name in self.feature_names]])
        raw = self.model.predict_proba(row)[:, 1]
        if self.calibrator is not None:
            raw = self.calibrator.predict_proba(raw.reshape(-1, 1))[:, 1]
        return float(raw[0])


class ModelTrainer:
    """Fits sequential fit/early-stop/calibration partitions; no random split."""

    def __init__(self, config: TrainingConfig | None = None) -> None:
        self.config = config or TrainingConfig()

    def fit(self, samples: tuple[LabeledSample, ...] | list[LabeledSample]) -> ModelArtifact:
        _, np, LGBMClassifier, early_stopping, LogisticRegression, average_precision_score, brier_score_loss, roc_auc_score = require_ml()
        ordered = tuple(sorted(samples, key=lambda item: item.features.as_of))
        if len(ordered) < 180:
            raise ValueError("At least 180 chronological ML samples are required for a shadow model.")
        names = tuple(sorted(ordered[0].features.values))
        if any(tuple(sorted(item.features.values)) != names for item in ordered):
            raise ValueError("ML feature schema changed inside the training sample.")
        x = np.array([[item.features.values[name] for name in names] for item in ordered], dtype=float)
        y = np.array([item.label.value for item in ordered], dtype=int)
        if len(set(y.tolist())) < 2:
            raise ValueError("Training labels need both target and non-target outcomes.")
        fit_end, early_end = int(len(ordered) * 0.70), int(len(ordered) * 0.85)
        if len(set(y[:fit_end].tolist())) < 2 or len(set(y[fit_end:early_end].tolist())) < 2:
            raise ValueError("Each chronological training partition needs both outcome classes.")
        model = LGBMClassifier(
            objective="binary", max_depth=self.config.max_depth, learning_rate=self.config.learning_rate,
            n_estimators=self.config.n_estimators, min_child_samples=self.config.min_child_samples,
            reg_alpha=self.config.reg_alpha, reg_lambda=self.config.reg_lambda,
            random_state=self.config.random_state, n_jobs=1, verbosity=-1,
        )
        model.fit(
            x[:fit_end], y[:fit_end], eval_set=[(x[fit_end:early_end], y[fit_end:early_end])],
            callbacks=[early_stopping(self.config.early_stopping_rounds, verbose=False)],
        )
        calibration_x, calibration_y = x[early_end:], y[early_end:]
        raw = model.predict_proba(calibration_x)[:, 1]
        calibrator = LogisticRegression(C=1.0, max_iter=500, random_state=self.config.random_state)
        calibrator.fit(raw.reshape(-1, 1), calibration_y)
        probability = calibrator.predict_proba(raw.reshape(-1, 1))[:, 1]
        metrics = TrainingMetrics(
            samples=len(calibration_y), positive_rate=float(calibration_y.mean()),
            roc_auc=_metric_or_none(roc_auc_score, calibration_y, probability),
            average_precision=_metric_or_none(average_precision_score, calibration_y, probability),
            brier_score=float(brier_score_loss(calibration_y, probability)),
        )
        importances = dict(zip(names, model.feature_importances_.tolist(), strict=True))
        return ModelArtifact(
            model=model, calibrator=calibrator, feature_names=names, feature_importance=importances,
            trained_at=datetime.now(timezone.utc), trained_until=ordered[-1].features.as_of,
            config=self.config, calibration_metrics=metrics,
        )


def artifact_metadata(artifact: ModelArtifact) -> dict[str, object]:
    """Metadata stored beside the model, deliberately excluding fitted objects."""
    return {
        "schema_version": 1,
        "trained_at": artifact.trained_at.isoformat(), "trained_until": artifact.trained_until.isoformat(),
        "feature_names": list(artifact.feature_names), "feature_importance": artifact.feature_importance,
        "config": asdict(artifact.config), "calibration_metrics": asdict(artifact.calibration_metrics),
        "mode": "shadow_only",
    }


def _metric_or_none(metric, truth, probability):  # type: ignore[no-untyped-def]
    return float(metric(truth, probability)) if len(set(truth.tolist())) > 1 else None
