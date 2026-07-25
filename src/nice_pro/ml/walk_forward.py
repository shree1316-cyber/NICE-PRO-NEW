"""Strict chronological rolling validation for the ML shadow experiment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import mean

from nice_pro.ml.contracts import LabeledSample
from nice_pro.ml.runtime import require_ml
from nice_pro.ml.trainer import ModelTrainer, TrainingConfig


@dataclass(frozen=True, slots=True)
class WalkForwardConfig:
    training_sessions: int = 120
    test_sessions: int = 20
    embargo_sessions: int = 1
    minimum_test_samples: int = 30


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    train_from: date
    train_to: date
    test_from: date
    test_to: date
    samples: int
    roc_auc: float | None
    precision: float | None
    expectancy_r: float | None
    profit_factor: float | None


class WalkForwardValidator:
    """Never shuffles. One full session embargo prevents label overlap."""

    def __init__(self, config: WalkForwardConfig | None = None, training: TrainingConfig | None = None) -> None:
        self.config = config or WalkForwardConfig()
        self.training = training or TrainingConfig()

    def validate(self, samples: tuple[LabeledSample, ...] | list[LabeledSample]) -> tuple[WalkForwardFold, ...]:
        _, _, _, _, _, _, _, roc_auc_score = require_ml()
        ordered = tuple(sorted(samples, key=lambda item: item.features.as_of))
        sessions = sorted({item.features.as_of.date() for item in ordered})
        folds: list[WalkForwardFold] = []
        start = 0
        while start + self.config.training_sessions + self.config.embargo_sessions + self.config.test_sessions <= len(sessions):
            train_days = set(sessions[start:start + self.config.training_sessions])
            test_start = start + self.config.training_sessions + self.config.embargo_sessions
            test_days = set(sessions[test_start:test_start + self.config.test_sessions])
            train = tuple(item for item in ordered if item.features.as_of.date() in train_days)
            test = tuple(item for item in ordered if item.features.as_of.date() in test_days)
            if len(test) >= self.config.minimum_test_samples:
                artifact = ModelTrainer(self.training).fit(train)
                probabilities = [artifact.predict_probability(item.features.values) for item in test]
                labels = [item.label.value for item in test]
                predicted = [value >= 0.5 for value in probabilities]
                positives = sum(predicted)
                true_positive = sum(guess and bool(label) for guess, label in zip(predicted, labels, strict=True))
                wins = sum(labels)
                losses = len(labels) - wins
                win_rate = wins / len(labels)
                folds.append(WalkForwardFold(
                    sessions[start], sessions[start + self.config.training_sessions - 1], sessions[test_start], sessions[test_start + self.config.test_sessions - 1],
                    len(test), float(roc_auc_score(labels, probabilities)) if len(set(labels)) > 1 else None,
                    true_positive / positives if positives else None,
                    1.5 * win_rate - (1 - win_rate),
                    (1.5 * wins / losses) if losses else None,
                ))
            start += self.config.test_sessions
        return tuple(folds)


def summary(folds: tuple[WalkForwardFold, ...]) -> dict[str, float | int | None]:
    return {
        "folds": len(folds),
        "mean_roc_auc": _mean(item.roc_auc for item in folds),
        "mean_precision": _mean(item.precision for item in folds),
        "mean_expectancy_r": _mean(item.expectancy_r for item in folds),
        "mean_profit_factor": _mean(item.profit_factor for item in folds),
    }


def _mean(values):  # type: ignore[no-untyped-def]
    usable = [value for value in values if value is not None]
    return float(mean(usable)) if usable else None
