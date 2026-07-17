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

## Safety boundary

There is no order-placement code. `NICE_PAPER_TRADING_ONLY` defaults to `true`. Kite's subscription tokens are explicit configuration, must be checked against the latest instrument master before every market session, and do not authorize trading.
