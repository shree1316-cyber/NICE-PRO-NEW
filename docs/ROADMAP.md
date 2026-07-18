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

## Completed — Milestone 3: Indicator and regime engine

- Seed history from Kite historical candles
- VWAP, EMA, RSI, ATR, volume and opening-range features
- Trend/range/volatile regime classification
- Dashboard market-structure panel

## Completed — Milestone 4: Options analytics and conviction inputs

- ATM strike discovery and option subscriptions
- Open interest, put-call ratio, IV and premium-velocity inputs
- Bullish/bearish reason contracts for the future conviction engine

## Completed — Milestone 5: Conviction and trade-plan engine

- Configurable, category-based bullish/bearish scores
- Explicit evidence and conflict reasons
- Trade-quality grades, risk limits, and paper-trade-only plans

## Completed — Milestone 6: Live analysis workspaces and expanded option context

- Full NIFTY and SENSEX workspaces: live price, indicator values, evidence, conflicts, score, grade and paper plan
- Live NIFTY and SENSEX option-chain tables with CE/PE LTP, OI, session OI delta, model IV and premium velocity
- Expanded default ATM range to five strikes on each side (configurable)
- Observed ATM straddle, IV skew and observed max-pain context, clearly labelled as subscribed-strike calculations
- Correct live connection status handling and no fabricated `0.00 / 0.00` bid/ask values

## Next — Milestone 7: Paper trading, journal, and reports

- Paper positions and stop/target lifecycle simulation
- Trade journal with evidence captured at entry
- Daily performance and quality-grade reports

## Later milestones

1. Indicators and market-regime classification
2. Options-chain and premium analytics
3. Conviction, conflict, grade, and alert engines
4. Paper trading, journal, reports, and backtesting
5. Evidence-based parameter calibration
