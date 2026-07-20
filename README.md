# NICE-PRO

NIFTY & SENSEX Intraday Conviction Engine — a transparent, paper-trading-first desktop decision-support application.

> **Status:** Milestone 9. The NIFTY/SENSEX indicator matrix displays every configured indicator across 10s, 30s, 1m, 5m, 15m, 30m and 1h. The paper-plan decision now uses a transparent multi-timeframe gate; each value is calculated only from its corresponding timeframe.

## Principles

- No guaranteed signals or profit claims.
- Explainable evidence, including conflicting signals, before every trade plan.
- Paper trading and validation before any optional live execution.
- Zerodha credentials stay only in a local `.env` file and must never be committed.

## Quick start

1. Install Python 3.11 or newer.
2. Create and activate a virtual environment.
3. Run `python -m pip install --upgrade pip setuptools`.
4. Run `python -m pip install -e . --no-build-isolation`.
5. Copy `.env.example` to `.env`; credentials are optional for offline dashboard mode.
6. Add valid Kite credentials to receive live data. Never commit `.env`.
7. Verify the instrument tokens in `NICE_SUBSCRIPTIONS` against Kite's current instrument master before every market session.
8. The default `NICE_OPTION_CHAIN_SCOPE=full_current_expiry` subscribes to every listed CE and PE strike in the nearest active expiry. Set it to `atm_window` only for a lower-bandwidth diagnostic window; then `NICE_OPTION_STRIKES_EACH_SIDE` controls the ATM range.
9. Run `python -m nice_pro`.

Run the checks with `python -m pytest`. See [Run NICE-PRO](docs/RUN_NICE_PRO.md) for the Windows step-by-step guide.

## Architecture

`Kite service → Event bus → Market state → Analysis engines → Dashboard`

The app streams only explicitly subscribed market data. By default it subscribes to the **complete nearest-expiry NIFTY and SENSEX CE/PE chains**, so PCR, Max Pain, IV skew, and option metrics cover every listed strike in that expiry once their initial quotes arrive. Later weekly/monthly expiries are intentionally separate chains. A Kite WebSocket connection accepts at most 3,000 instruments, and NICE-PRO stops with an explicit status message rather than silently showing partial data if that limit would be exceeded.

For desktop responsiveness, NICE-PRO retains every live option tick but recalculates and repaints the complete-chain table once per second. The small `atm_window` diagnostic mode refreshes its compact table up to four times per second.

### Multi-timeframe paper-plan gate

- **10s / 30s (5% each):** entry timing only; they never reverse the wider thesis.
- **1m (20%) + 5m (25%):** must agree on direction before a paper plan is eligible.
- **15m (20%), 30m (15%), 1h (10%):** confirmation filters; a direct opposing signal blocks the plan.
- The **5m core score** remains visible for auditability, while the MTF gate remains the final paper-plan decision layer.

### Futures-volume proxy

At startup NICE-PRO discovers and subscribes to the nearest current-month NIFTY and SENSEX futures. Their exchange-traded volume is overlaid on the corresponding spot-index candles solely to calculate the volume indicator category. Each volume row identifies this as a **futures-volume proxy**, never as spot-index volume.

The timeframe weights are deliberately category-level safeguards, not a claim that all 100 indicator rows are independent votes. They must be validated with paper-trade and historical results before being relied on. NICE-PRO contains no order-placement API. A trade plan is a paper-only candidate and is never an instruction or guarantee.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/ROADMAP.md](docs/ROADMAP.md).
