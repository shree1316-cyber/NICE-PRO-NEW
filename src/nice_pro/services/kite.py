"""Kite Connect boundary for quotes only; it contains no order-placement API."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from kiteconnect import KiteConnect, KiteTicker
from loguru import logger

from nice_pro.config.settings import Settings, Subscription
from nice_pro.models.market import Quote

TickCallback = Callable[[Quote], None]
StatusCallback = Callable[[str], None]


class KiteService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: KiteConnect | None = None
        self._ticker: KiteTicker | None = None

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

        symbols = {subscription.instrument_token: subscription.symbol for subscription in subscriptions}
        tokens = list(symbols)
        ticker = KiteTicker(self._settings.kite_api_key, self._settings.kite_access_token)

        def status(message: str) -> None:
            logger.info("Kite stream: {}", message)
            if on_status is not None:
                on_status(message)

        def on_connect(ws, response) -> None:  # type: ignore[no-untyped-def]
            del response
            ws.subscribe(tokens)
            ws.set_mode(ws.MODE_FULL, tokens)
            status(f"connected; subscribed to {len(tokens)} instruments")

        def on_ticks(ws, ticks) -> None:  # type: ignore[no-untyped-def]
            del ws
            for tick in ticks:
                token = tick.get("instrument_token")
                symbol = symbols.get(token)
                last_price = tick.get("last_price")
                if symbol is None or last_price is None:
                    continue
                depth = tick.get("depth", {})
                buy, sell = depth.get("buy", []), depth.get("sell", [])
                timestamp = tick.get("exchange_timestamp") or tick.get("timestamp") or datetime.now(timezone.utc)
                on_quote(
                    Quote(
                        instrument_token=token,
                        symbol=symbol,
                        last_price=float(last_price),
                        received_at=timestamp,
                        volume=tick.get("volume_traded"),
                        bid=buy[0].get("price") if buy else None,
                        ask=sell[0].get("price") if sell else None,
                    )
                )

        ticker.on_connect = on_connect
        ticker.on_ticks = on_ticks
        ticker.on_close = lambda ws, code, reason: status(f"closed ({code}): {reason}")
        ticker.on_error = lambda ws, code, reason: status(f"error ({code}): {reason}")
        ticker.on_reconnect = lambda ws, attempts_count: status(f"reconnecting (attempt {attempts_count})")
        ticker.on_noreconnect = lambda ws: status("reconnect limit reached")
        self._ticker = ticker
        status("connecting")
        ticker.connect(threaded=True)

    def stop_stream(self) -> None:
        if self._ticker is not None:
            self._ticker.close()
            self._ticker = None
            logger.info("Kite stream stopped.")
