# NICE-PRO Architecture

## Milestone 3 flow

```text
KiteTicker (FULL quote mode)
          │
          ▼
Quote-only Kite service
          │
          ▼
Market data engine ──► 10s / 30s / 1m candle builders
          │
          ├── Thread-safe market state
          ├── Bounded 1-minute candle history
          ├── VWAP / EMA / RSI / ATR / relative volume / opening range
          └── Qt signals ──► PySide6 dashboard
```

`src/nice_pro` is the active application package. Earlier root-level prototype files are preserved temporarily for reference and will be retired once their successor modules exist.

The Kite callback runs in KiteTicker's worker thread. It never manipulates widgets directly; instead, it publishes a Qt signal that the desktop thread receives safely.

At startup, a worker fetches recent one-minute candles to warm the indicators. A failed warm-up is shown in the dashboard but cannot stop live quote handling.

## Options analytics and feed integrity

After a spot quote arrives, a worker reads Kite's instrument master, selects the nearest valid NIFTY or SENSEX expiry, and subscribes to **every CE/PE contract in that one expiry**. Later expiries are separate chains and are intentionally excluded. The option engine exposes direct LTP, OI, session OI change, best bid/ask, and Kite's available top-five depth. It derives premium velocity, Black–Scholes implied volatility, estimated CVD, OTM continuation, PCR, observed max pain, and ATM straddle from those quotes.

The dashboard always separates direct and derived fields. In particular:

- Top-five book imbalance is a liquidity/execution context, never a directional vote.
- Estimated CVD is not exchange CVD; Kite does not provide trade-aggressor flags.
- OTM continuation is a premium-velocity estimate, not an exchange-labelled flow event.
- A WebSocket interruption clears option quote history, premium velocity, and estimated CVD. These fields warm up again from fresh quotes.
- The chain header reports registered, quoted, and fresh contracts plus quote age. A Hero paper plan is blocked until the full nearest-expiry chain and both ATM legs are fresh.

## Conviction and plans

The conviction engine combines independent market-structure and option inputs into separately visible bullish and bearish scores. A confidence value measures evidence alignment, not a calibrated probability of profit. The 5-minute core is an audit score; the multi-timeframe gate decides whether a paper plan can be evaluated. A/A+ only creates a **paper-only** candidate plan if an ATM option quote is available, the required live inputs are fresh, and estimated loss per lot is below the configured cap. Audio alerts are cooldown-protected and never submit an order.

Research decisions are captured at most once per completed live 5-minute spot candle. History warm-up and futures-volume warm-up do not create records. A reconnect also clears pending journal capture, preventing a pre-outage candle from being combined with post-reconnect option flow.

## Safety boundary

There is no order-placement code. `NICE_PAPER_TRADING_ONLY` defaults to `true`. Kite's subscription tokens are explicit configuration, must be checked against the latest instrument master before every market session, and do not authorize trading.
