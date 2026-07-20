"""Application composition root."""

from collections.abc import Callable
from threading import RLock, Thread
from time import monotonic, sleep

from loguru import logger

from nice_pro.alerts.quality import QualityAlertEngine
from nice_pro.config.settings import Settings
from nice_pro.core.events import EventBus
from nice_pro.core.logging import configure_logging
from nice_pro.engines.conviction import ConvictionEngine
from nice_pro.engines.history import CandleHistory
from nice_pro.engines.indicators import IndicatorEngine
from nice_pro.engines.market_data import MarketDataEngine
from nice_pro.engines.market_state import MarketState
from nice_pro.engines.options import OptionChainEngine
from nice_pro.models.market import Candle, ConvictionSnapshot, IndicatorSnapshot, MarketSnapshot, OptionChainSnapshot, Quote
from nice_pro.services.kite import KiteService

ANALYSIS_TIMEFRAMES = (10, 30, 60, 300, 900, 1800, 3600)


class Application:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.events = EventBus()
        self.market_state = MarketState()
        self.market_data = MarketDataEngine(self.market_state)
        self.history = CandleHistory()
        self.indicators = IndicatorEngine()
        self.options = OptionChainEngine()
        self.conviction = ConvictionEngine()
        self.alerts = QualityAlertEngine()
        self.kite = KiteService(settings)
        self._analysis_by_underlying: dict[str, dict[int, IndicatorSnapshot]] = {}
        self._options_by_underlying: dict[str, OptionChainSnapshot] = {}
        self._option_lock = RLock()
        self._last_option_publish: dict[str, float] = {}
        # A complete nearest-expiry chain can contain hundreds of contracts.
        # Ticks are retained at full stream speed, while the expensive chain
        # analytics and table repaint are intentionally sampled at 1 Hz.
        self._option_publish_interval_seconds = (
            0.25 if settings.option_chain_scope == "atm_window" else 1.0
        )
        self._futures_by_token: dict[int, str] = {}
        self._future_symbols: dict[str, str] = {}
        self._spot_symbols = {"NIFTY": "NSE:NIFTY 50", "SENSEX": "BSE:SENSEX"}
        self._snapshot_listeners: list[Callable[[MarketSnapshot], None]] = []
        self._analysis_listeners: list[Callable[[IndicatorSnapshot], None]] = []
        self._option_listeners: list[Callable[[OptionChainSnapshot], None]] = []
        self._conviction_listeners: list[Callable[[ConvictionSnapshot], None]] = []
        self._status_listeners: list[Callable[[str], None]] = []

    def add_snapshot_listener(self, listener: Callable[[MarketSnapshot], None]) -> None:
        self._snapshot_listeners.append(listener)

    def add_analysis_listener(self, listener: Callable[[IndicatorSnapshot], None]) -> None:
        self._analysis_listeners.append(listener)

    def add_option_listener(self, listener: Callable[[OptionChainSnapshot], None]) -> None:
        self._option_listeners.append(listener)

    def add_conviction_listener(self, listener: Callable[[ConvictionSnapshot], None]) -> None:
        self._conviction_listeners.append(listener)

    def add_status_listener(self, listener: Callable[[str], None]) -> None:
        self._status_listeners.append(listener)

    def start(self) -> None:
        logger.info("Application started (paper trading only: {}).", self.settings.paper_trading_only)
        if self.settings.kite_configured:
            self.publish_status("starting Kite market-data services")
            self.kite.start_stream(self.settings.subscriptions, self.process_quote, self.publish_status)
            Thread(target=self._seed_history, name="candle-history-seed", daemon=True).start()
            Thread(target=self._discover_futures, name="futures-volume-feed", daemon=True).start()
            Thread(target=self._discover_option_chain, name="option-universe", daemon=True).start()
        else:
            self.publish_status("Kite credentials not configured — dashboard is in offline mode")

    def stop(self) -> None:
        self.kite.stop_stream()
        logger.info("Application stopped.")

    def process_quote(self, quote: Quote) -> None:
        future_underlying = self._futures_by_token.get(quote.instrument_token)
        if future_underlying is not None:
            # Futures remain a separate price stream.  Their completed candle
            # volumes are overlaid onto spot-index analysis as a labelled proxy.
            update = self.market_data.process(quote)
            for candle in update.closed_candles:
                self.history.append(candle)
                self._publish_analysis(self._spot_symbols[future_underlying], candle.timeframe_seconds)
            return
        if self.options.is_option_token(quote.instrument_token):
            chain: OptionChainSnapshot | None = None
            with self._option_lock:
                contract = self.options.ingest(quote)
                if contract is None:
                    return
                underlying = contract.underlying
                now = monotonic()
                if now - self._last_option_publish.get(underlying, 0.0) >= self._option_publish_interval_seconds:
                    chain = self.options.snapshot(underlying, self._spot(underlying))
                    self._last_option_publish[underlying] = now
            if chain is not None:
                self._publish_option(chain)
            return
        update = self.market_data.process(quote)
        for listener in tuple(self._snapshot_listeners):
            listener(update.snapshot)
        for candle in update.closed_candles:
            self.history.append(candle)
            self._publish_analysis(candle.symbol, candle.timeframe_seconds)

    def publish_status(self, message: str) -> None:
        for listener in tuple(self._status_listeners):
            listener(message)

    def _seed_history(self) -> None:
        self.publish_status("warming up one-minute indicator history")
        for subscription in self.settings.subscriptions:
            try:
                logger.info("History warm-up started for {}", subscription.symbol)
                candles = self.kite.historical_minute_candles(subscription, lookback_days=15)
                if not candles:
                    raise RuntimeError("Kite returned no one-minute candles")
                self.history.extend(candles)
                for timeframe_seconds in ANALYSIS_TIMEFRAMES:
                    self._publish_analysis(subscription.symbol, timeframe_seconds)
                logger.info("History warm-up completed for {}: {} candles", subscription.symbol, len(candles))
                self.publish_status(f"history ready for {subscription.symbol}: {len(candles)} candles")
            except Exception as error:
                logger.exception("History warm-up failed for {}", subscription.symbol)
                self.publish_status(f"history warm-up failed for {subscription.symbol}: {error}")
        self.publish_status("live quote stream active")

    def _discover_futures(self) -> None:
        """Attach current-month futures as the real exchange-volume proxy."""
        for underlying in ("NIFTY", "SENSEX"):
            try:
                future = self.kite.nearest_future_subscription(underlying)
                if future is None:
                    self.publish_status(f"futures volume proxy unavailable for {underlying}")
                    continue
                self._futures_by_token[future.instrument_token] = underlying
                self._future_symbols[underlying] = future.symbol
                self.kite.add_subscriptions((future,))
                self.publish_status(f"{underlying} futures-volume proxy subscribed")
                logger.info("Futures volume proxy for {}: {}", underlying, future.symbol)
                candles = self.kite.historical_minute_candles(future, lookback_days=15)
                if not candles:
                    raise RuntimeError("Kite returned no futures minute candles")
                self.history.extend(candles)
                for timeframe_seconds in ANALYSIS_TIMEFRAMES:
                    self._publish_analysis(self._spot_symbols[underlying], timeframe_seconds)
                self.publish_status(f"{underlying} futures-volume history ready: {len(candles)} candles")
            except Exception as error:
                logger.exception("Futures volume proxy setup failed for {}", underlying)
                self.publish_status(f"futures volume proxy failed for {underlying}: {error}")

    def _discover_option_chain(self) -> None:
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
                if self.settings.option_chain_scope == "atm_window":
                    contracts = self.kite.nearest_option_contracts(
                        underlying, spot, strikes_each_side=self.settings.option_strikes_each_side
                    )
                    coverage = "ATM observation window"
                else:
                    contracts = self.kite.current_expiry_option_contracts(underlying)
                    coverage = "complete nearest-expiry chain"
                if not contracts:
                    self.publish_status(f"no current {underlying} option contracts found")
                    continue
                # Check before registering any contracts. This avoids a chain
                # being displayed as complete if Kite cannot stream all of it.
                self.kite.require_subscription_capacity(contracts)
                with self._option_lock:
                    self.options.register(contracts)
                self.kite.add_subscriptions(contracts)
                self.publish_status(f"{underlying} {coverage} subscribed: {len(contracts)} CE/PE contracts")
                logger.info("{} {} subscribed: {} contracts", underlying, coverage, len(contracts))
                with self._option_lock:
                    chain = self.options.snapshot(underlying, spot)
                self._publish_option(chain)
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

    def _publish_analysis(self, symbol: str, timeframe_seconds: int) -> None:
        underlying = "NIFTY" if "NIFTY" in symbol else "SENSEX"
        candles = self.history.for_symbol(symbol, timeframe_seconds)
        future_symbol = self._future_symbols.get(underlying)
        volume_source = "Spot-index candle volume"
        if future_symbol is not None:
            candles = _with_futures_volume(
                candles, self.history.for_symbol(future_symbol, timeframe_seconds)
            )
            volume_source = f"Current-month {underlying} futures volume proxy"
        snapshot = self.indicators.evaluate(
            symbol, candles, timeframe_seconds, volume_source=volume_source
        )
        self._analysis_by_underlying.setdefault(underlying, {})[timeframe_seconds] = snapshot
        for listener in tuple(self._analysis_listeners):
            listener(snapshot)
        # Re-assess whenever a timeframe closes.  The engine requires 1m and
        # 5m alignment before it can create a paper plan.
        self._evaluate_conviction(underlying)

    def _publish_option(self, snapshot: OptionChainSnapshot) -> None:
        self._options_by_underlying[snapshot.underlying] = snapshot
        for listener in tuple(self._option_listeners):
            listener(snapshot)
        self._evaluate_conviction(snapshot.underlying)

    def _evaluate_conviction(self, underlying: str) -> None:
        analyses = self._analysis_by_underlying.get(underlying, {})
        # Five minutes is the stable core model.  The 1m snapshot remains an
        # entry/confirmation input inside the multi-timeframe gate.
        analysis = analyses.get(300)
        options = self._options_by_underlying.get(underlying)
        if analysis is None or options is None:
            return
        snapshot = self.conviction.evaluate(analysis, options, analyses)
        for listener in tuple(self._conviction_listeners):
            listener(snapshot)
        if self.alerts.should_alert(snapshot):
            self.alerts.play(snapshot.grade)
            self.publish_status(f"{snapshot.underlying} {snapshot.grade} paper-trade setup alert")


def run_desktop() -> None:
    from nice_pro.dashboard.main_window import run_dashboard

    settings = Settings.load()
    configure_logging(settings.log_level)
    run_dashboard(Application(settings))


def _with_futures_volume(
    spot_candles: tuple[Candle, ...], future_candles: tuple[Candle, ...]
) -> tuple[Candle, ...]:
    """Keep spot OHLC while using matched futures bars only for traded volume."""
    future_volumes = {candle.opened_at: candle.volume for candle in future_candles}
    return tuple(
        Candle(
            symbol=candle.symbol,
            timeframe_seconds=candle.timeframe_seconds,
            opened_at=candle.opened_at,
            closed_at=candle.closed_at,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=future_volumes.get(candle.opened_at, 0),
        )
        for candle in spot_candles
    )
