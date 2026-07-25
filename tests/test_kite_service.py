<<<<<<< Updated upstream
from datetime import date, datetime, timedelta, timezone
=======
from datetime import date, timedelta
>>>>>>> Stashed changes

import pytest

pytest.importorskip("kiteconnect")

from nice_pro.config.settings import Settings
from nice_pro.models.market import OptionType
from nice_pro.services.kite import KiteService


def test_current_expiry_option_contracts_returns_all_nearest_strikes(monkeypatch) -> None:
    service = KiteService(Settings("key", "secret", "token"))
    today = date.today()
    first_expiry, later_expiry = today + timedelta(days=2), today + timedelta(days=9)
    records = [
        {
            "name": "NIFTY",
            "instrument_type": option_type,
            "expiry": expiry,
            "instrument_token": token,
            "tradingsymbol": f"NIFTY{token}{option_type}",
            "strike": strike,
            "lot_size": 75,
        }
        for token, expiry, strike, option_type in (
            (1, first_expiry, 24000, "CE"),
            (2, first_expiry, 24000, "PE"),
            (3, first_expiry, 24100, "CE"),
            (4, first_expiry, 24100, "PE"),
            (5, later_expiry, 24200, "CE"),
        )
    ]
    monkeypatch.setattr(service, "_instruments", lambda exchange: records)

    contracts = service.current_expiry_option_contracts("NIFTY")

    assert [(contract.strike, contract.option_type) for contract in contracts] == [
        (24000.0, OptionType.CALL),
        (24000.0, OptionType.PUT),
        (24100.0, OptionType.CALL),
        (24100.0, OptionType.PUT),
    ]
<<<<<<< Updated upstream


def test_stream_health_marks_an_old_live_stream_as_stale() -> None:
    service = KiteService(Settings("key", "secret", "token"))
    service._stream_state = "LIVE"  # Test the presentation boundary only.
    service._last_tick_at = datetime.now(timezone.utc) - timedelta(seconds=11)

    health = service.stream_health(stale_after_seconds=10)

    assert health["state"] == "STALE"
    assert health["last_tick_age_seconds"] is not None
=======
>>>>>>> Stashed changes
