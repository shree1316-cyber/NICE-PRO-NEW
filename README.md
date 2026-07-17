# NICE-PRO

NIFTY & SENSEX Intraday Conviction Engine — a transparent, paper-trading-first desktop decision-support application.

> **Status:** Milestone 1 foundation. The desktop shell runs without Kite credentials. Live WebSocket ingestion, indicators, scoring, paper trades, and backtests are scheduled for later milestones.

## Principles

- No guaranteed signals or profit claims.
- Explainable evidence, including conflicting signals, before every trade plan.
- Paper trading and validation before any optional live execution.
- Zerodha credentials stay only in a local `.env` file and must never be committed.

## Quick start

1. Install Python 3.11 or newer.
2. Create and activate a virtual environment.
3. Run `python -m pip install -r requirements.txt`.
4. Copy `.env.example` to `.env`; credentials are optional for Milestone 1.
5. Run `python -m nice_pro`.

Run the checks with `python -m pytest`.

## Architecture

`Kite service → Event bus → Market state → Analysis engines → Dashboard`

The Kite service is intentionally a non-streaming skeleton in this milestone. It never places orders and does not subscribe to market data yet.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/ROADMAP.md](docs/ROADMAP.md).
