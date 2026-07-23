"""Lazy optional dependency loading so the desktop app stays lightweight."""


class MLDependencyError(RuntimeError):
    """Raised only when a user invokes an ML command without its extras."""


def require_ml():  # type: ignore[no-untyped-def]
    try:
        import joblib
        import numpy
        from lightgbm import LGBMClassifier, early_stopping
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
    except ImportError as error:
        raise MLDependencyError(
            'Install the optional ML research package first: pip install -e ".[ml]"'
        ) from error
    return joblib, numpy, LGBMClassifier, early_stopping, LogisticRegression, average_precision_score, brier_score_loss, roc_auc_score
