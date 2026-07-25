from datetime import datetime, timezone
from pathlib import Path

from nice_pro.ml.service import MLShadowService
from nice_pro.models.market import IndicatorSnapshot, MarketRegime, Side


def test_missing_model_is_explicitly_shadow_not_trained(tmp_path: Path) -> None:
    service = MLShadowService(tmp_path)
    snapshot = IndicatorSnapshot(
        symbol="NSE:NIFTY 50", timeframe_seconds=300,
        calculated_at=datetime.now(timezone.utc), close=24000.0,
        regime=MarketRegime.RANGE,
    )
    result = service.evaluate("NIFTY", snapshot)
    assert result.score is None
    assert result.status == "MODEL NOT TRAINED"
