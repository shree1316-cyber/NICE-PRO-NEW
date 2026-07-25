import pytest

from nice_pro.ml.runtime import MLDependencyError, require_ml


def test_optional_ml_dependency_error_is_actionable() -> None:
    try:
        require_ml()
    except MLDependencyError as error:
        assert '".[ml]"' in str(error)
    except Exception as error:  # pragma: no cover - installed ML is also valid.
        pytest.fail(f"Unexpected optional-dependency failure: {error}")
