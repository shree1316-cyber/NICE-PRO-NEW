"""Kite Connect boundary for quotes only; it contains no order-placement API."""

from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta, timezone
from threading import RLock

from kiteconnect import KiteConnect, KiteTicker
from loguru import logger

from nice_pro.config.settings import Settings, Subscription
from nice_pro.engines.indicators import IST
from nice_pro.models.market import Candle, OptionContract, OptionType, Quote

TickCallback = Callable[[Quote], None]
StatusCallback = Callable[[str], None]


class KiteService:
    MAX_WEBSOCKET_SUBSCRIPTIONS = 3000

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: KiteConnect | None = None
        self._ticker: KiteTicker | None = None
        self._symbols: dict[int, str] = {}
        self._symbols_lock = RLock()
        self._instrument_cache: dict[str, list[dict[str, object]]] = {}
        self._instrument_lock = RLock()

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
        """Verify credentials without blocking an async caller."""
        import asyncio

        return await asyncio.to_thread(self.client().profile)

    def historical_minute_candles(self, subscription: Subscription, lookback_days: int = 2) -> list[Candle]:
        """Fetch completed one-minute candles for indicator warm-up.

        This is read-only historical data. Call it from a worker thread, not from
        the PySide desktop thread.
        """
        end = datetime.now(timezone.utc)
        rows = self.client().historical_data(
            subscription.instrument_token,
            end - timedelta(days=lookback_days),
            end,
            "minute",
        )
        candles: list[Candle] = []
        for row in rows:
            opened_at = row["date"]
            # Kite historical timestamps are exchanged in India market time and
            # are often naive datetime objects.  Attach IST rather than UTC.
            if opened_at.tzinfo is None:
                opened_at = opened_at.replace(tzinfo=IST)
            candles.append(
                Candle(
                    symbol=subscription.symbol,
                    timeframe_seconds=60,
                    opened_at=opened_at,
                    closed_at=opened_at + timedelta(minutes=1),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row.get("volume") or 0),
                )
            )
        return candles

    def nearest_option_contracts(
        self, underlying: str, spot: float, strikes_each_side: int = 2
    ) -> list[OptionContract]:
        """Return CE/PE contracts around ATM for the nearest valid expiry.

        The instrument master is the source of truth; no option token is hardcoded.
        """
        exchange = "NFO" if underlying == "NIFTY" else "BFO"
        today = date.today()
        records = [
            item
            for item in self._instruments(exchange)
            if item.get("name") == underlying
            and item.get("instrument_type") in {OptionType.CALL.value, OptionType.PUT.value}
            and item.get("expiry")
            and item["expiry"] >= today
        ]
        if not records:
            return []
        expiry = min(item["expiry"] for item in records)
        expiry_records = [item for item in records if item["expiry"] == expiry]
        strikes = sorted({float(item["strike"]) for item in expiry_records})
        atm_index = min(range(len(strikes)), key=lambda index: abs(strikes[index] - spot))
        selected = set(strikes[max(0, atm_index - strikes_each_side) : atm_index + strikes_each_side + 1])
        contracts: list[OptionContract] = []
        for item in expiry_records:
            strike = float(item["strike"])
            if strike not in selected:
                continue
            contracts.append(
                OptionContract(
                    instrument_token=int(item["instrument_token"]),
                    symbol=f"{exchange}:{item['tradingsymbol']}",
                    underlying=underlying,
                    expiry=item["expiry"],
                    strike=strike,
                    option_type=OptionType(item["instrument_type"]),
                    lot_size=int(item.get("lot_size") or 1),
                )
            )
        return contracts

    def current_expiry_option_contracts(self, underlying: str) -> list[OptionContract]:
        """Return every listed CE and PE strike for the nearest active expiry.

        This is the complete chain for one expiry available through Kite's
        instrument master. Later expiries are deliberately excluded because
        they are separate option chains and could exceed Kite's 3,000-token
        WebSocket subscription limit.
        """
        exchange = "NFO" if underlying == "NIFTY" else "BFO"
        today = date.today()
        records = [
            item
            for item in self._instruments(exchange)
            if item.get("name") == underlying
            and item.get("instrument_type") in {OptionType.CALL.value, OptionType.PUT.value}
            and item.get("expiry")
            and item["expiry"] >= today
        ]
        if not records:
            return []
        expiry = min(item["expiry"] for item in records)
        contracts = [
            OptionContract(
                instrument_token=int(item["instrument_token"]),
                symbol=f"{exchange}:{item['tradingsymbol']}",
                underlying=underlying,
                expiry=item["expiry"],
                strike=float(item["strike"]),
                option_type=OptionType(str(item["instrument_type"])),
                lot_size=int(item.get("lot_size") or 1),
            )
            for item in records
            if item["expiry"] == expiry
        ]
        return sorted(contracts, key=lambda contract: (contract.strike, contract.option_type))

    def nearest_future_subscription(self, underlying: str) -> Subscription | None:
        """Discover the nearest current-month index future from Kite's master.

        The future is used only as a labelled exchange-volume proxy for the
        related spot-index analysis.  It is never substituted for spot price.
        """
        exchange = "NFO" if underlying == "NIFTY" else "BFO"
        today = date.today()
        records = [
            item
            for item in self._instruments(exchange)
            if item.get("name") == underlying
            and item.get("instrument_type") == "FUT"
            and item.get("expiry")
            and item["expiry"] >= today
        ]
        if not records:
            return None
        contract = min(records, key=lambda item: item["expiry"])
        return Subscription(
            symbol=f"{exchange}:{contract['tradingsymbol']}",
            instrument_token=int(contract["instrument_token"]),
        )

    def start_stream(
        self,
        subscriptions: Sequence[Subscription],
        on_quote: TickCallback,
        on_status: StatusCallback | None = None,
    ) -> None:
        """Start a threaded KiteTicker subscription for the supplied instruments only."""
        if not self.configured:
            raise RuntimeError("Kite API is not configured. Add credentials to .env first.")
        if not subscriptions:
            raise ValueError("At least one explicit subscription is required.")
        if self._ticker is not None:
            logger.warning("Kite stream is already running.")
            return

        with self._symbols_lock:
            self._symbols = {subscription.instrument_token: subscription.symbol for subscription in subscriptions}
        ticker = KiteTicker(self._settings.kite_api_key, self._settings.kite_access_token)

        def status(message: str) -> None:
            logger.info("Kite stream: {}", message)
            if on_status is not None:
                on_status(message)

        def on_connect(ws, response) -> None:  # type: ignore[no-untyped-def]
            del response
            with self._symbols_lock:
                tokens = list(self._symbols)
            ws.subscribe(tokens)
            ws.set_mode(ws.MODE_FULL, tokens)
            status(f"connected; subscribed to {len(tokens)} instruments")

        tick_error_reported = False

        def on_ticks(ws, ticks) -> None:  # type: ignore[no-untyped-def]
            nonlocal tick_error_reported
            del ws
            for tick in ticks:
                token = tick.get("instrument_token")
                with self._symbols_lock:
                    symbol = self._symbols.get(token)
                last_price = tick.get("last_price")
                if symbol is None or last_price is None:
                    continue
                depth = tick.get("depth", {})
                buy, sell = depth.get("buy", []), depth.get("sell", [])
                top_bid_quantity = buy[0].get("quantity") if buy else None
                top_ask_quantity = sell[0].get("quantity") if sell else None
                bid_depth_quantity = sum(int(level.get("quantity") or 0) for level in buy) if buy else None
                ask_depth_quantity = sum(int(level.get("quantity") or 0) for level in sell) if sell else None
                timestamp = _normalise_kite_timestamp(
                    tick.get("exchange_timestamp") or tick.get("timestamp")
                )
                try:
                    on_quote(
                        Quote(
                            instrument_token=token,
                            symbol=symbol,
                            last_price=float(last_price),
                            received_at=timestamp,
                            volume=tick.get("volume_traded"),
                            bid=buy[0].get("price") if buy else None,
                            ask=sell[0].get("price") if sell else None,
                            open_interest=tick.get("oi"),
                            last_quantity=tick.get("last_quantity"),
                            top_bid_quantity=top_bid_quantity,
                            top_ask_quantity=top_ask_quantity,
                            bid_depth_quantity=bid_depth_quantity,
                            ask_depth_quantity=ask_depth_quantity,
                        )
                    )
                except Exception:
                    # Never let one bad tick tear down KiteTicker's reactor.
                    logger.exception("Tick processing failed for {}", symbol)
                    if not tick_error_reported:
                        status("tick processing error; see logs/nice-pro.log")
                        tick_error_reported = True

        ticker.on_connect = on_connect
        ticker.on_ticks = on_ticks
        ticker.on_close = lambda ws, code, reason: status(f"closed ({code}): {reason}")
        ticker.on_error = lambda ws, code, reason: status(f"error ({code}): {reason}")
        ticker.on_reconnect = lambda ws, attempts_count: status(f"reconnecting (attempt {attempts_count})")
        ticker.on_noreconnect = lambda ws: status("reconnect limit reached")
        self._ticker = ticker
        status("connecting")
        ticker.connect(threaded=True)

    def add_subscriptions(self, contracts: Sequence[OptionContract | Subscription]) -> None:
        """Dynamically subscribe discovered option or futures contracts."""
        if self._ticker is None:
            raise RuntimeError("Start the spot stream before adding option subscriptions.")
        self.require_subscription_capacity(contracts)
        with self._symbols_lock:
            new_tokens = [contract.instrument_token for contract in contracts if contract.instrument_token not in self._symbols]
            self._symbols.update({contract.instrument_token: contract.symbol for contract in contracts})
        if new_tokens:
            self._ticker.subscribe(new_tokens)
            self._ticker.set_mode(self._ticker.MODE_FULL, new_tokens)
            logger.info("Subscribed to {} additional market-data instruments.", len(new_tokens))

    def require_subscription_capacity(self, contracts: Sequence[OptionContract | Subscription]) -> None:
        """Fail before registering a partial chain when Kite's token cap is reached."""
        with self._symbols_lock:
            new_tokens = {contract.instrument_token for contract in contracts if contract.instrument_token not in self._symbols}
            available = self.MAX_WEBSOCKET_SUBSCRIPTIONS - len(self._symbols)
        if len(new_tokens) > available:
            raise RuntimeError(
                f"Kite WebSocket capacity exceeded: need {len(new_tokens)} additional instruments, "
                f"but only {available} of {self.MAX_WEBSOCKET_SUBSCRIPTIONS} slots remain."
            )

    def _instruments(self, exchange: str) -> list[dict[str, object]]:
        """Load one instrument-master copy per exchange for this application run."""
        with self._instrument_lock:
            cached = self._instrument_cache.get(exchange)
            if cached is not None:
                return cached
        instruments = self.client().instruments(exchange)
        with self._instrument_lock:
            self._instrument_cache[exchange] = instruments
        return instruments

    def stop_stream(self) -> None:
        if self._ticker is not None:
            self._ticker.close()
            self._ticker = None
            logger.info("Kite stream stopped.")


def _normalise_kite_timestamp(value: object | None) -> datetime:
    """Return an aware UTC timestamp for a Kite tick.

    Kite may return naive IST datetimes for exchange timestamps.  Mixing those
    with the aware UTC fallback clock makes duration calculations fail.
    """
    if not isinstance(value, datetime):
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=IST)
    return value.astimezone(timezone.utc)
