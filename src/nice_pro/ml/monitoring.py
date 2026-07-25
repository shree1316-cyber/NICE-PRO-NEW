"""Conservative feature-importance tracking for manual retraining reviews."""

from __future__ import annotations

import json
from pathlib import Path

from nice_pro.ml.trainer import ModelArtifact


class FeatureImportanceTracker:
    """Flags persistently weak features; it never removes them automatically."""

    def __init__(self, path: Path = Path("data/ml_models/importance_history.json")) -> None:
        self.path = path

    def record(self, artifact: ModelArtifact) -> None:
        history = self._read()
        history.append(artifact.feature_importance)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(history[-12:], indent=2), encoding="utf-8")

    def review_flags(self, minimum_gain: float = 1.0, cycles: int = 3) -> tuple[str, ...]:
        history = self._read()
        if len(history) < cycles:
            return ()
        recent = history[-cycles:]
        names = set().union(*(item.keys() for item in recent))
        return tuple(sorted(name for name in names if all(float(item.get(name, 0.0)) < minimum_gain for item in recent)))

    def _read(self) -> list[dict[str, float]]:
        if not self.path.exists():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (OSError, ValueError):
            return []
