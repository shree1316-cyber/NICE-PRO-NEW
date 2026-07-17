"""Application composition root."""

import asyncio

from loguru import logger

from nice_pro.config.settings import Settings
from nice_pro.core.events import EventBus
from nice_pro.core.logging import configure_logging
from nice_pro.dashboard.main_window import run_dashboard
from nice_pro.engines.market_state import MarketState
from nice_pro.services.kite import KiteService


class Application:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.events = EventBus()
        self.market_state = MarketState()
        self.kite = KiteService(settings)

    async def start(self) -> None:
        logger.info("Application services started (paper trading only: {}).", self.settings.paper_trading_only)

    async def stop(self) -> None:
        logger.info("Application services stopped.")


def run_desktop() -> None:
    settings = Settings.load()
    configure_logging(settings.log_level)
    application = Application(settings)
    asyncio.run(application.start())
    try:
        run_dashboard(settings)
    finally:
        asyncio.run(application.stop())
