"""Local model registry with explicit metadata and no automatic promotion."""

from __future__ import annotations

import json
from pathlib import Path

from nice_pro.ml.runtime import require_ml
from nice_pro.ml.trainer import ModelArtifact, artifact_metadata


class ModelRegistry:
    def __init__(self, directory: Path = Path("data/ml_models")) -> None:
        self.directory = directory

    def save_shadow(self, artifact: ModelArtifact, name: str = "latest_shadow") -> tuple[Path, Path]:
        joblib, *_ = require_ml()
        self.directory.mkdir(parents=True, exist_ok=True)
        model_path = self.directory / f"{name}.joblib"
        metadata_path = self.directory / f"{name}.json"
        joblib.dump(artifact, model_path)
        metadata_path.write_text(json.dumps(artifact_metadata(artifact), indent=2), encoding="utf-8")
        return model_path, metadata_path

    def load_shadow(self, name: str = "latest_shadow") -> ModelArtifact:
        joblib, *_ = require_ml()
        return joblib.load(self.directory / f"{name}.joblib")
