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
        )

    @property
    def kite_configured(self) -> bool:
        return bool(self.kite_api_key and self.kite_access_token)
