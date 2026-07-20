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

### Live microstructure fields

- **Bid-Ask Spread:** direct average of the live ATM CE/PE best bid and best ask.
- **ATM Book Imbalance:** direct, normalized imbalance from Kite's available top-five bid/offer quantities for the ATM CE/PE pair.
- **Estimated CVD:** live estimate using price-versus-quote classification and available trade size. Kite does not supply exchange aggressor flags, so this must not be treated as true exchange CVD.
- **OTM Continuation:** live chain-derived estimate from the first OTM call and put premium velocities. It is not an exchange-labelled event.

### Full-chain Hero Conviction

The Options page includes separate NIFTY and SENSEX **Hero** boxes. They use only nearest-expiry chain inputs: PCR, total and changing call/put OI, ATM IV skew, straddle, expected move, direct bid-ask spread, top-five book imbalance, estimated CVD, and derived OTM continuation. Its directional score is a true 100-point budget: PCR 20, total OI 7, OI change 13, IV skew 12, book imbalance 17, estimated CVD 17, and OTM continuation 14. A Hero plan is strictly paper-only and appears only for an A/A+ option-chain grade with a live ATM quote and risk inside the per-lot cap. Confidence measures the coverage and agreement of the live chain evidence; it is not a probability of profit. The Hero model does not use price-action or multi-timeframe evidence and is not a trading guarantee.

### Indicator matrix summary and scalp box

The dashboard quote cards show a compact, **5-minute indicator-matrix audit**. It counts bullish and bearish readings within Trend (20 points), Momentum (20), Volatility (15), Levels (15), Volume (15), and Options & Flow (15). A category's points are proportional to the number of its rows currently classified bullish or bearish; neutral, informational, and missing-data rows do not create a vote.

The Options page also contains a separate **Scalping Box** for each index. Its 100-point paper-only framework requires: 10s/30s directional alignment (30), direct top-five ATM book imbalance (25), estimated CVD (20), OTM continuation (15), and ATM premium-velocity leadership (10). An acceptable ATM spread is an execution-quality gate. A scalp plan needs a score of at least 70, confidence of at least 65, no unresolved data conflicts, a live ATM quote, and risk within the configured per-lot cap. Stops are 8% of premium, with targets at 1.08× and 1.15× entry; these are configurable model parameters, not guarantees.

The timeframe weights are deliberately category-level safeguards, not a claim that all 100 indicator rows are independent votes. They must be validated with paper-trade and historical results before being relied on. NICE-PRO contains no order-placement API. A trade plan is a paper-only candidate and is never an instruction or guarantee.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/ROADMAP.md](docs/ROADMAP.md).
