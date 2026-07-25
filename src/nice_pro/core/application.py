"""Application composition root."""

from collections.abc import Callable
from datetime import datetime, timezone
from threading import Event, RLock, Thread
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
from nice_pro.engines.option_hero import OptionHeroEngine
from nice_pro.engines.scalp import ScalpEngine
from nice_pro.journal.store import ResearchJournal
from nice_pro.ml.service import MLShadowService, MLShadowStatus
from nice_pro.models.market import Candle, ConvictionSnapshot, IndicatorSnapshot, MarketSnapshot, OptionChainSnapshot, OptionHeroSnapshot, Quote, ScalpSnapshot
from nice_pro.papertrade.policy import ForwardTestPolicy
from nice_pro.papertrade.tracker import PaperTradeTracker
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
        self.option_hero = OptionHeroEngine()
        self.scalp = ScalpEngine()
        self.conviction = ConvictionEngine()
        # Core ML reads the shared cached 5-minute snapshot only. Its own
        # candle-only candidate direction is independent of the 308D policy,
        # option Hero, scalp, and any later Live-Enriched model.
        self.ml_shadow = MLShadowService()
        self.journal = ResearchJournal(settings.journal_database_path)
        self.forward_policy = ForwardTestPolicy(
            policy_id=settings.forward_test_policy_id,
            enabled=settings.forward_test_enabled,
        )
        self.paper_trades = PaperTradeTracker(self.journal, self.forward_policy)
        self.alerts = QualityAlertEngine()
        self.kite = KiteService(settings)
        self._analysis_by_underlying: dict[str, dict[int, IndicatorSnapshot]] = {}
        self._options_by_underlying: dict[str, OptionChainSnapshot] = {}
        self._option_lock = RLock()
        self._journal_lock = RLock()
        self._stop_requested = Event()
        self._last_option_publish: dict[str, float] = {}
        self._last_journal_candle: dict[str, object] = {}
        self._pending_journal_candle: dict[str, object] = {}
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
        self._option_hero_listeners: list[Callable[[OptionHeroSnapshot], None]] = []
        self._scalp_listeners: list[Callable[[ScalpSnapshot], None]] = []
        self._conviction_listeners: list[Callable[[ConvictionSnapshot], None]] = []
        self._ml_shadow_by_underlying: dict[str, MLShadowStatus] = {}
        self._status_listeners: list[Callable[[str], None]] = []

    def add_snapshot_listener(self, listener: Callable[[MarketSnapshot], None]) -> None:
        self._snapshot_listeners.append(listener)

    def add_analysis_listener(self, listener: Callable[[IndicatorSnapshot], None]) -> None:
        self._analysis_listeners.append(listener)

    def add_option_listener(self, listener: Callable[[OptionChainSnapshot], None]) -> None:
        self._option_listeners.append(listener)

    def add_option_hero_listener(self, listener: Callable[[OptionHeroSnapshot], None]) -> None:
        self._option_hero_listeners.append(listener)

    def add_scalp_listener(self, listener: Callable[[ScalpSnapshot], None]) -> None:
        self._scalp_listeners.append(listener)

    def add_conviction_listener(self, listener: Callable[[ConvictionSnapshot], None]) -> None:
        self._conviction_listeners.append(listener)

    def add_status_listener(self, listener: Callable[[str], None]) -> None:
        self._status_listeners.append(listener)

    def start(self) -> None:
        self._stop_requested.clear()
        logger.info("Application started (paper trading only: {}).", self.settings.paper_trading_only)
        if self.forward_policy.enabled:
            self.publish_status(
                "forward policy active: MTF 65+, A/A+, 15-minute cooldown, 3 entries/day"
            )
        else:
            self.publish_status("forward policy disabled; paper entries will not be opened")
        if self.settings.kite_configured:
            self.publish_status("starting Kite market-data services")
            self.kite.start_stream(
                self.settings.subscriptions,
                self.process_quote,
                self.publish_status,
                self._on_stream_reset,
            )
            Thread(target=self._seed_history, name="candle-history-seed", daemon=True).start()
            Thread(target=self._discover_futures, name="futures-volume-feed", daemon=True).start()
            Thread(target=self._discover_option_chain, name="option-universe", daemon=True).start()
        else:
            self.publish_status("Kite credentials not configured — dashboard is in offline mode")

        Thread(target=self._run_eod_paper_guard, name="paper-eod-guard", daemon=True).start()

    def stop(self) -> None:
        self._stop_requested.set()
        self.kite.stop_stream()
        logger.info("Application stopped.")

    def forward_policy_status(self, underlying: str) -> dict[str, object]:
        """Return paper-forward controls for an honest dashboard explanation."""
        return self.paper_trades.policy_status(underlying)

    def ml_shadow_status(self, underlying: str) -> MLShadowStatus | None:
        """Latest ML display result; it cannot alter paper-plan eligibility."""
        return self._ml_shadow_by_underlying.get(underlying)

    def feed_health(self) -> dict[str, object]:
        """Expose the current stream state without implying feed completeness."""
        if not self.settings.kite_configured:
            return {"state": "OFFLINE", "last_tick_age_seconds": None, "reconnect_count": 0}
        return self.kite.stream_health()

    def data_feed_statuses(self) -> dict[str, str]:
        """Describe direct, derived, and unavailable feeds for the dashboard."""
        future_status = "LIVE FUTURES-VOLUME PROXY" if len(self._future_symbols) == 2 else "FUTURES PROXY SUBSCRIBING"
        chains = tuple(self._options_by_underlying.values())
        if chains and all(item.atm_book_imbalance is not None for item in chains):
            book_status = "DIRECT TOP-5 DEPTH (LIQUIDITY CONTEXT)"
        elif chains:
            book_status = "TOP-5 DEPTH WARMING UP"
        else:
            book_status = "OPTION DEPTH SUBSCRIBING"
        return {
            "index_futures": future_status,
            "option_book": book_status,
            "derived": "ESTIMATED CVD / OTM FLOW (REBASED AFTER RECONNECT)",
            "india_vix": "NOT CONNECTED",
            "market_breadth": "NOT CONNECTED",
            "global_cues": "NOT CONNECTED",
        }

    def process_quote(self, quote: Quote) -> None:
        future_underlying = self._futures_by_token.get(quote.instrument_token)
        if future_underlying is not None:
            # Futures remain a separate price stream.  Their completed candle
            # volumes are overlaid onto spot-index analysis as a labelled proxy.
            update = self.market_data.process(quote)
            for candle in update.closed_candles:
                self.history.append(candle)
                self._publish_analysis(
                    self._spot_symbols[future_underlying], candle.timeframe_seconds
                )
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
            self._publish_analysis(
                candle.symbol,
                candle.timeframe_seconds,
                journal_eligible=candle.timeframe_seconds == 300,
            )

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

    def _publish_analysis(
        self, symbol: str, timeframe_seconds: int, *, journal_eligible: bool = False
    ) -> None:
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
        if journal_eligible and timeframe_seconds == 300:
            # Only a live, completed spot 5m candle can create a journal event
            # or open a forward-test position.  History/futures warm-up never
            # gets treated as a new trading decision.
            with self._journal_lock:
                self._pending_journal_candle[underlying] = snapshot.calculated_at
        # Re-assess whenever a timeframe closes.  The engine requires 1m and
        # 5m alignment before it can create a paper plan.
        self._evaluate_conviction(underlying)

    def _publish_option(self, snapshot: OptionChainSnapshot) -> None:
        self._options_by_underlying[snapshot.underlying] = snapshot
        for listener in tuple(self._option_listeners):
            listener(snapshot)
        hero = self.option_hero.evaluate(snapshot)
        for listener in tuple(self._option_hero_listeners):
            listener(hero)
        scalp = self.scalp.evaluate(snapshot, self._analysis_by_underlying.get(snapshot.underlying, {}))
        for listener in tuple(self._scalp_listeners):
            listener(scalp)
        self._evaluate_conviction(snapshot.underlying)

    def _on_stream_reset(self, reason: str) -> None:
        """Rebase derived option-flow data after a WebSocket interruption."""
        with self._option_lock:
            self.options.reset_derived_metrics()
            self._options_by_underlying.clear()
            self._last_option_publish.clear()
        # Do not create a decision from a pre-outage 5-minute candle using
        # post-reconnect option data.  The next completed live 5-minute candle
        # will create a fresh research snapshot once the chain has warmed up.
        with self._journal_lock:
            self._pending_journal_candle.clear()
        self.publish_status(f"option-derived metrics rebasing after {reason}")

    def _evaluate_conviction(self, underlying: str) -> None:
        analyses = self._analysis_by_underlying.get(underlying, {})
        # Five minutes is the stable core model.  The 1m snapshot remains an
        # entry/confirmation input inside the multi-timeframe gate.
        analysis = analyses.get(300)
        options = self._options_by_underlying.get(underlying)
        if analysis is None or options is None:
            return
        snapshot = self.conviction.evaluate(analysis, options, analyses)
        self._ml_shadow_by_underlying[underlying] = self.ml_shadow.evaluate(underlying, analysis)
        decision_id: int | None = None
        # Save at most one research-grade decision only for a live completed
        # 5-minute *spot* candle.  This lock prevents concurrent warm-up,
        # futures, and option-stream workers from duplicating the same candle.
        with self._journal_lock:
            pending = self._pending_journal_candle.get(underlying)
            if (
                pending == analysis.calculated_at
                and self._last_journal_candle.get(underlying) != analysis.calculated_at
            ):
                hero = self.option_hero.evaluate(options)
                scalp = self.scalp.evaluate(options, analyses)
                decision_id = self.journal.capture_decision(snapshot, analyses, options, hero, scalp)
                self._last_journal_candle[underlying] = analysis.calculated_at
                self._pending_journal_candle.pop(underlying, None)
        opened = self.paper_trades.evaluate(snapshot, options, decision_id)
        for listener in tuple(self._conviction_listeners):
            listener(snapshot)
        active = self.paper_trades.active_position(underlying)
        if opened and self.alerts.should_alert(
            snapshot,
            policy=self.forward_policy,
            decision_id=decision_id,
            active_decision_id=active.decision_id if active is not None else None,
            chain=options,
        ):
            self.alerts.play(snapshot.grade)
            self.publish_status(f"{snapshot.underlying} {snapshot.grade} paper-trade setup alert")

    def _run_eod_paper_guard(self) -> None:
        """Ensure active policy papers receive a durable 15:20 IST exit."""
        while not self._stop_requested.wait(5):
            with self._option_lock:
                chains = dict(self._options_by_underlying)
            closed = self.paper_trades.force_exit_due(chains, datetime.now(timezone.utc))
            for underlying in closed:
                self.publish_status(f"{underlying} paper position closed by scheduled EOD safeguard")


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
