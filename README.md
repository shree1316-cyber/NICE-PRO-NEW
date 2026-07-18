# NICE-PRO

NIFTY & SENSEX Intraday Conviction Engine — a transparent, paper-trading-first desktop decision-support application.

> **Status:** Milestone 6. Live quote streaming, focused NIFTY/SENSEX analysis workspaces, expanded observed ATM option-chain data, explainable conviction, and paper-only candidate plans are implemented. Paper-trade journaling, reports, and backtesting follow in later milestones.

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

The app streams only explicitly subscribed market data. The option-chain page labels its Max Pain and similar figures as **observed** because the calculation uses subscribed strikes rather than every exchange strike. It contains no order-placement API. A trade plan is a paper-only candidate and is never an instruction or guarantee.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/ROADMAP.md](docs/ROADMAP.md).
