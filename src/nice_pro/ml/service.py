"""Fail-safe ML shadow service for the live dashboard.

It reads the existing in-memory indicator snapshot, makes no Kite API request,
and cannot open an order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nice_pro.ml.features import build_feature_row
from nice_pro.ml.inference import ShadowInferenceEngine
from nice_pro.ml.registry import ModelRegistry
from nice_pro.ml.runtime import MLDependencyError
from nice_pro.models.market import IndicatorSnapshot, Side


@dataclass(frozen=True, slots=True)
class MLShadowStatus:
    underlying: str
    calculated_at: datetime
    score: float | None
    status: str
    regime: str
    top_reasons: tuple[str, ...] = ()


class MLShadowService:
    """Loads one explicitly trained local model for display-only inference."""

    def __init__(self, directory: Path = Path("data/ml_models")) -> None:
        self._registry = ModelRegistry(directory)
        self._model_path = directory / "latest_shadow.joblib"
        self._engine: ShadowInferenceEngine | None = None
        self._load_error: str | None = None
        self._load_if_available()

    def _load_if_available(self) -> None:
        if not self._model_path.exists():
            return
        try:
            self._engine = ShadowInferenceEngine(self._registry.load_shadow())
        except MLDependencyError:
            self._load_error = "ML DEPENDENCIES MISSING"
        except (OSError, ValueError, TypeError):
            self._load_error = "MODEL UNAVAILABLE"

    def evaluate(self, underlying: str, analysis: IndicatorSnapshot, side: Side) -> MLShadowStatus:
        row = build_feature_row(analysis, side)
        if self._engine is None:
            return MLShadowStatus(underlying, analysis.calculated_at, None, self._load_error or "MODEL NOT TRAINED", row.regime.value)
        if side is Side.NEUTRAL:
            return MLShadowStatus(underlying, analysis.calculated_at, None, "WAITING FOR RULE DIRECTION", row.regime.value)
        result = self._engine.evaluate(row)
        return MLShadowStatus(underlying, analysis.calculated_at, result.probability, result.status, row.regime.value, result.top_reasons)
