"""Safe Kite Connect boundary. Live streaming will be added in Milestone 2."""

from collections.abc import Awaitable, Callable

from kiteconnect import KiteConnect
from loguru import logger

from nice_pro.config.settings import Settings
from nice_pro.models.market import Quote


TickCallback = Callable[[Quote], Awaitable[None]]


class KiteService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: KiteConnect | None = None

    @property
    def configured(self) -> bool:
        return self._settings.kite_configured

    def client(self) -> KiteConnect:
        if not self.configured:
            raise RuntimeError("Kite API is not configured. Add credentials to .env first.")
        if self._client is None:
            self._client = KiteConnect(api_key=self._settings.kite_api_key)
            self._client.set_access_token(self._settings.kite_access_token)
        return self._client

    async def verify_session(self) -> dict[str, object]:
        """Verify credentials without blocking the application event loop."""
        import asyncio

        return await asyncio.to_thread(self.client().profile)

    async def start_stream(self, on_quote: TickCallback) -> None:
        """Placeholder for KiteTicker wiring in Milestone 2.

        No subscriptions or orders are created here. This explicit boundary prevents
        accidental live-market behaviour while the app foundation is being tested.
        """
        del on_quote
        logger.info("Kite streaming is not enabled in Milestone 1.")
