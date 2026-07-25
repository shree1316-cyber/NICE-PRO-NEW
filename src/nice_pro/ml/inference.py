"""Live-compatible shadow inference. It never approves an order."""

from dataclasses import dataclass

from nice_pro.ml.contracts import FeatureRow
from nice_pro.ml.trainer import ModelArtifact


@dataclass(frozen=True, slots=True)
class ShadowInference:
    probability: float
    status: str
    top_reasons: tuple[str, ...]


class ShadowInferenceEngine:
    def __init__(self, artifact: ModelArtifact, threshold: float = 0.82) -> None:
        self.artifact = artifact
        self.threshold = threshold

    def evaluate(self, row: FeatureRow) -> ShadowInference:
        probability = self.artifact.predict_probability(row.values)
        top = sorted(self.artifact.feature_importance, key=self.artifact.feature_importance.get, reverse=True)[:3]
        reasons = tuple(
            f"{name}: {row.values.get(name, 0.0):.3f} (global model importance {self.artifact.feature_importance[name]:.0f})"
            for name in top
        )
        status = "SHADOW HIGH" if probability >= self.threshold else "SHADOW OBSERVE"
        return ShadowInference(probability, status, reasons)
