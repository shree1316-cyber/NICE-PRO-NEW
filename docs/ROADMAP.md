# NICE-PRO Roadmap

## Completed — Milestone 1: Foundation

- Installable Python package and repeatable dependency setup
- Environment-based settings and secret-safe `.env` convention
- Structured logging, event bus, market models, and in-memory market state
- Safe Kite Connect boundary with no streaming or order placement
- Runnable PySide6 dashboard shell
- Unit tests and base documentation

## Completed — Milestone 2: Live market data

- Instrument lookup and explicit NIFTY/SENSEX subscriptions
- KiteTicker lifecycle and reconnect handling
- Tick validation and event publication
- 10-second, 30-second, and 1-minute candle aggregation
- Live dashboard price cards

## Next — Milestone 3: Indicator and regime engine

- Seed history from Kite historical candles
- VWAP, EMA, RSI, ATR, volume and opening-range features
- Trend/range/volatile regime classification
- Dashboard market-structure panel

## Later milestones

1. Indicators and market-regime classification
2. Options-chain and premium analytics
3. Conviction, conflict, grade, and alert engines
4. Paper trading, journal, reports, and backtesting
5. Evidence-based parameter calibration
