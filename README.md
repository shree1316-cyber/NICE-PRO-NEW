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
8. Adjust `NICE_OPTION_STRIKES_EACH_SIDE` only when needed. The default `5` subscribes to the ATM strike plus five strikes on each side, for CE and PE contracts.
9. Run `python -m nice_pro`.

Run the checks with `python -m pytest`. See [Run NICE-PRO](docs/RUN_NICE_PRO.md) for the Windows step-by-step guide.

## Architecture

`Kite service → Event bus → Market state → Analysis engines → Dashboard`

The app streams only explicitly subscribed market data. The option-chain page labels its Max Pain and similar figures as **observed** because the calculation uses subscribed strikes rather than every exchange strike.

### Multi-timeframe paper-plan gate

- **10s / 30s (5% each):** entry timing only; they never reverse the wider thesis.
- **1m (20%) + 5m (25%):** must agree on direction before a paper plan is eligible.
- **15m (20%), 30m (15%), 1h (10%):** confirmation filters; a direct opposing signal blocks the plan.
- The **5m core score** remains visible for auditability, while the MTF gate remains the final paper-plan decision layer.

The timeframe weights are deliberately category-level safeguards, not a claim that all 100 indicator rows are independent votes. They must be validated with paper-trade and historical results before being relied on. NICE-PRO contains no order-placement API. A trade plan is a paper-only candidate and is never an instruction or guarantee.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/ROADMAP.md](docs/ROADMAP.md).
