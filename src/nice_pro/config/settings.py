"""Typed, environment-backed configuration."""

from dataclasses import dataclass
from os import getenv
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    kite_api_key: str
    kite_api_secret: str
    kite_access_token: str
    log_level: str = "INFO"
    dashboard_refresh_ms: int = 500
    paper_trading_only: bool = True
    option_strikes_each_side: int = 5
    option_chain_scope: str = "full_current_expiry"
    journal_database_path: Path = Path("data/nice_pro_journal.sqlite3")
    forward_test_enabled: bool = True
    forward_test_policy_id: str = "NIFTY_CORE_308D_V1"
    subscriptions: tuple["Subscription", ...] = ()

    @classmethod
    def load(cls, env_file: Path | None = None) -> "Settings":
        load_dotenv(env_file, override=False)
        return cls(
            kite_api_key=getenv("KITE_API_KEY", ""),
            kite_api_secret=getenv("KITE_API_SECRET", ""),
            kite_access_token=getenv("KITE_ACCESS_TOKEN", ""),
            log_level=getenv("NICE_LOG_LEVEL", "INFO").upper(),
            dashboard_refresh_ms=int(getenv("NICE_DASHBOARD_REFRESH_MS", "500")),
            paper_trading_only=getenv("NICE_PAPER_TRADING_ONLY", "true").lower()
            in {"1", "true", "yes", "on"},
            option_strikes_each_side=max(1, int(getenv("NICE_OPTION_STRIKES_EACH_SIDE", "5"))),
            option_chain_scope=getenv("NICE_OPTION_CHAIN_SCOPE", "full_current_expiry").strip().lower(),
            journal_database_path=Path(getenv("NICE_JOURNAL_DATABASE", "data/nice_pro_journal.sqlite3")),
            forward_test_enabled=getenv("NICE_FORWARD_TEST_ENABLED", "true").lower()
            in {"1", "true", "yes", "on"},
            forward_test_policy_id=getenv("NICE_FORWARD_TEST_POLICY_ID", "NIFTY_CORE_308D_V1").strip(),
            subscriptions=_parse_subscriptions(
                getenv("NICE_SUBSCRIPTIONS", "NSE:NIFTY 50:256265,BSE:SENSEX:265")
            ),
        )

    @property
    def kite_configured(self) -> bool:
        return bool(self.kite_api_key and self.kite_access_token)


@dataclass(frozen=True, slots=True)
class Subscription:
    """An explicit KiteTicker instrument subscription.

    Tokens can change after exchange migrations. Confirm them in Kite's instrument
    master before a live session and override NICE_SUBSCRIPTIONS when required.
    """

    symbol: str
    instrument_token: int


def _parse_subscriptions(value: str) -> tuple[Subscription, ...]:
    subscriptions: list[Subscription] = []
    for item in value.split(","):
        exchange, symbol, token = (part.strip() for part in item.rsplit(":", 2))
        subscriptions.append(Subscription(symbol=f"{exchange}:{symbol}", instrument_token=int(token)))
    return tuple(subscriptions)
