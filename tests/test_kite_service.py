from datetime import date, timedelta

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
