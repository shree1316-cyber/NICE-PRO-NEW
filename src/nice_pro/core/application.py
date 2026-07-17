"""Application composition root."""

from collections.abc import Callable
from threading import Thread
from time import sleep

from loguru import logger

from nice_pro.config.settings import Settings
from nice_pro.core.events import EventBus
from nice_pro.core.logging import configure_logging
from nice_pro.engines.history import CandleHistory
from nice_pro.engines.indicators import IndicatorEngine
from nice_pro.engines.market_data import MarketDataEngine
from nice_pro.engines.market_state import MarketState
from nice_pro.engines.options import OptionChainEngine
from nice_pro.models.market import IndicatorSnapshot, MarketSnapshot, OptionChainSnapshot, Quote
from nice_pro.services.kite import KiteService


class Application:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.events = EventBus()
        self.market_state = MarketState()
        self.market_data = MarketDataEngine(self.market_state)
        self.history = CandleHistory()
        self.indicators = IndicatorEngine()
        self.options = OptionChainEngine()
        self.kite = KiteService(settings)
        self._snapshot_listeners: list[Callable[[MarketSnapshot], None]] = []
        self._analysis_listeners: list[Callable[[IndicatorSnapshot], None]] = []
        self._option_listeners: list[Callable[[OptionChainSnapshot], None]] = []
        self._status_listeners: list[Callable[[str], None]] = []

    def add_snapshot_listener(self, listener: Callable[[MarketSnapshot], None]) -> None:
        self._snapshot_listeners.append(listener)

    def add_analysis_listener(self, listener: Callable[[IndicatorSnapshot], None]) -> None:
        self._analysis_listeners.append(listener)

    def add_option_listener(self, listener: Callable[[OptionChainSnapshot], None]) -> None:
        self._option_listeners.append(listener)

    def add_status_listener(self, listener: Callable[[str], None]) -> None:
        self._status_listeners.append(listener)

    def start(self) -> None:
        logger.info("Application started (paper trading only: {}).", self.settings.paper_trading_only)
        if self.settings.kite_configured:
            self.kite.start_stream(self.settings.subscriptions, self.process_quote, self.publish_status)
            Thread(target=self._seed_history, name="candle-history-seed", daemon=True).start()
            Thread(target=self._discover_atm_options, name="option-universe", daemon=True).start()
        else:
            self.publish_status("Kite credentials not configured — dashboard is in offline mode")

    def stop(self) -> None:
        self.kite.stop_stream()
        logger.info("Application stopped.")

    def process_quote(self, quote: Quote) -> None:
        if self.options.is_option_token(quote.instrument_token):
            underlying = self._underlying_from_option_symbol(quote.symbol)
            chain = self.options.update(quote, self._spot(underlying))
            if chain is not None:
                self._publish_option(chain)
            return
        update = self.market_data.process(quote)
        for listener in tuple(self._snapshot_listeners):
            listener(update.snapshot)
        for candle in update.closed_candles:
            if candle.timeframe_seconds == 60:
                self.history.append(candle)
                self._publish_analysis(candle.symbol)

    def publish_status(self, message: str) -> None:
        for listener in tuple(self._status_listeners):
            listener(message)

    def _seed_history(self) -> None:
        self.publish_status("warming up one-minute indicator history")
        for subscription in self.settings.subscriptions:
            try:
                self.history.extend(self.kite.historical_minute_candles(subscription))
                self._publish_analysis(subscription.symbol)
            except Exception as error:
                logger.exception("History warm-up failed for {}", subscription.symbol)
                self.publish_status(f"history warm-up failed for {subscription.symbol}: {error}")
        self.publish_status("live quote stream active")

    def _discover_atm_options(self) -> None:
        """Wait for each index spot price, then subscribe to a narrow ATM option universe."""
        for subscription in self.settings.subscriptions:
            underlying = "NIFTY" if "NIFTY" in subscription.symbol else "SENSEX"
            for _ in range(30):
                spot = self._spot(underlying)
                if spot is not None:
                    break
                sleep(1)
            else:
                self.publish_status(f"option discovery skipped for {underlying}: no spot quote")
                continue
            try:
                contracts = self.kite.nearest_option_contracts(underlying, spot)
                if not contracts:
                    self.publish_status(f"no current {underlying} option contracts found")
                    continue
                self.options.register(contracts)
                self.kite.add_subscriptions(contracts)
                self._publish_option(self.options.snapshot(underlying, spot))
            except Exception as error:
                logger.exception("Option discovery failed for {}", underlying)
                self.publish_status(f"option discovery failed for {underlying}: {error}")

    def _spot(self, underlying: str) -> float | None:
        symbol = "NSE:NIFTY 50" if underlying == "NIFTY" else "BSE:SENSEX"
        quote = self.market_state.snapshot.quote_for(symbol)
        return quote.last_price if quote is not None else None

    @staticmethod
    def _underlying_from_option_symbol(symbol: str) -> str:
        return "NIFTY" if "NIFTY" in symbol else "SENSEX"

    def _publish_analysis(self, symbol: str) -> None:
        snapshot = self.indicators.evaluate(symbol, self.history.for_symbol(symbol))
        for listener in tuple(self._analysis_listeners):
            listener(snapshot)

    def _publish_option(self, snapshot: OptionChainSnapshot) -> None:
        for listener in tuple(self._option_listeners):
            listener(snapshot)


def run_desktop() -> None:
    from nice_pro.dashboard.main_window import run_dashboard

    settings = Settings.load()
    configure_logging(settings.log_level)
    run_dashboard(Application(settings))
