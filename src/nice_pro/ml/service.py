"""Fail-safe ML shadow service for the live dashboard.

It reads the existing in-memory indicator snapshot, makes no Kite API request,
and cannot open an order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nice_pro.ml.features import CORE_ML_CONTRACT, build_feature_row, derive_core_ml_side
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
        self._directory = directory
        self._registry = ModelRegistry(directory)
        self._engines: dict[str, ShadowInferenceEngine] = {}
        self._model_mtimes: dict[str, int] = {}
        self._load_errors: dict[str, str] = {}

    def _engine_for(self, underlying: str) -> ShadowInferenceEngine | None:
        key = underlying.upper()
        model_name = f"latest_shadow_{key.lower()}"
        model_path = self._directory / f"{model_name}.joblib"
        if not model_path.exists():
            self._engines.pop(key, None)
            self._model_mtimes.pop(key, None)
            self._load_errors[key] = "MODEL NOT TRAINED"
            return None
        metadata_path = self._directory / f"{model_name}.json"
        # A v1 file was trained with the 308D rule direction. It must never be
        # presented as an independent Core-ML result.
        if not metadata_path.exists() or CORE_ML_CONTRACT not in metadata_path.read_text(encoding="utf-8"):
            self._engines.pop(key, None)
            self._model_mtimes.pop(key, None)
            self._load_errors[key] = "CORE ML RE-TRAIN REQUIRED"
            return None
        modified = model_path.stat().st_mtime_ns
        if self._model_mtimes.get(key) == modified:
            return self._engines.get(key)
        try:
            self._engines[key] = ShadowInferenceEngine(self._registry.load_shadow(model_name))
            self._model_mtimes[key] = modified
            self._load_errors.pop(key, None)
        except MLDependencyError:
            self._load_errors[key] = "ML DEPENDENCIES MISSING"
        except (OSError, ValueError, TypeError):
            self._load_errors[key] = "MODEL UNAVAILABLE"
        return self._engines.get(key)

    def evaluate(self, underlying: str, analysis: IndicatorSnapshot) -> MLShadowStatus:
        # No input from the 308D policy or option engines is accepted here.
        row = build_feature_row(analysis)
        engine = self._engine_for(underlying)
        if engine is None:
            return MLShadowStatus(
                underlying,
                analysis.calculated_at,
                None,
                self._load_errors.get(underlying.upper(), "MODEL NOT TRAINED"),
                row.regime.value,
            )
        if derive_core_ml_side(analysis) is Side.NEUTRAL:
            return MLShadowStatus(underlying, analysis.calculated_at, None, "WAITING FOR CORE ML DIRECTION", row.regime.value)
        result = engine.evaluate(row)
        return MLShadowStatus(underlying, analysis.calculated_at, result.probability, result.status, row.regime.value, result.top_reasons)
