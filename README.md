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

### Live microstructure fields and reconnect safety

- **Bid-Ask Spread:** direct average of the live ATM CE/PE best bid and best ask.
- **ATM Book Imbalance:** direct, normalized imbalance from Kite's available top-five bid/offer quantities for the ATM CE/PE pair. It is an **execution-liquidity context only**; NICE-PRO does not treat combined call/put depth as a directional order-flow vote.
- **Estimated CVD:** live estimate using price-versus-quote classification and available trade size. Kite does not supply exchange aggressor flags, so this must not be treated as true exchange CVD.
- **OTM Continuation:** live chain-derived estimate from the first OTM call and put premium velocities. It is not an exchange-labelled event.

The dashboard distinguishes direct data, derived estimates, unavailable feeds, and stream health. After a Kite WebSocket interruption, NICE-PRO clears option premium history and estimated CVD before accepting fresh values again. Estimated CVD remains marked as warming up until two consecutive fresh quotes have arrived for an option. The option summary displays registered, quoted, and fresh-contract coverage plus ATM/oldest quote age; “complete” refers only to the current nearest expiry, not later expiries. A Hero paper plan is blocked until the full subscribed nearest-expiry chain and ATM pair are fresh.

### Full-chain Hero Conviction

The Options page includes separate NIFTY and SENSEX **Hero** boxes. They use only nearest-expiry chain inputs: PCR plus aggregate OI corroboration, changing call/put OI, ATM IV skew, straddle, expected move, direct bid-ask spread, top-five depth availability, estimated CVD, derived OTM continuation, and ATM premium velocity. Its raw directional-evidence score is a true 100-point budget: OI-position group 35 (PCR 25 plus corroboration 10), OI change 15, IV skew 10, estimated CVD 18, OTM continuation 12, and ATM premium velocity 10. Top-five depth is an execution/liquidity check, not a directional weight.

Hero grades use the normalized directional-evidence score: **A+ = 80--100** (and at most one unresolved conflict), **A = 65--79** (and at most two), **B = 45--64**, **C = 25--44**, and **Avoid = below 25 or mixed directional evidence**. A Hero plan is strictly paper-only and appears only for an A/A+ option-chain grade with a fresh ATM quote and risk inside the per-lot cap. The Hero box labels this explicitly as a **raw chain bias**: it is not forward-policy validation, a probability of profit, or a win-rate forecast. “Evidence quality” measures live-data coverage and agreement, not certainty.

### Indicator matrix summary and scalp box

The dashboard quote cards show a compact, **5-minute indicator-matrix audit**. It counts bullish and bearish readings within Trend (20 points), Momentum (20), Volatility (15), Levels (15), Volume (15), and Options & Flow (15). A category's points are proportional to the number of its rows currently classified bullish or bearish; neutral, informational, and missing-data rows do not create a vote.

The Options page also contains a separate **Scalping Box** for each index. Its 100-point paper-only framework requires: aligned 10s/30s direction (40), estimated CVD (25), OTM continuation (20), and ATM premium-velocity leadership (15). Top-five ATM depth and an acceptable spread are execution-quality gates, not direction weights. If raw option-flow bias conflicts with 10s/30s timing, the displayed execution direction becomes **WAIT / CONFLICT** even if the raw score is high. A scalp plan needs a score of at least 70, evidence quality of at least 65, no unresolved conflicts, a fresh ATM quote, and risk within the configured per-lot cap. Stops are 8% of premium, with targets at 1.08x and 1.15x entry; these are configurable model parameters, not guarantees.

The timeframe weights are deliberately category-level safeguards, not a claim that all 100 indicator rows are independent votes. They must be validated with paper-trade and historical results before being relied on. NICE-PRO contains no order-placement API. A trade plan is a paper-only candidate and is never an instruction or guarantee.

### Research journal and 10-day reports

The **Journal** page stores a local, decision-time research snapshot for every completed **5-minute core candle** after the market, option-chain and MTF models are ready. Each snapshot contains the seven timeframe readings, all configured indicator-matrix rows, core/MTF scores and gate, reasons/conflicts, full nearest-expiry chain metrics, Hero/Scalp assessments, the independent Core-ML shadow score/status/regime/top features, and a versioned Live-Enriched observation envelope. The latter is collection-only: it stores live chain/depth-proxy/freshness context for a future separately validated model and does not train or change a trade decision. Raw records are stored in UTC for reproducible research, while the dashboard displays their timestamps in **IST**. The local SQLite file defaults to `data/nice_pro_journal.sqlite3` and can be relocated through `NICE_JOURNAL_DATABASE`.

The default forward-paper policy is `NIFTY_CORE_308D_V1`, based on the selected **NIFTY** 308-session core candidate: MTF score at least 65, grade A/A+, a fresh completed 5-minute spot decision, a 15-minute cooldown after a close, no more than three entries per IST day, and a 15:20 IST forced end-of-day close. It does not open SENSEX forward positions until a separately validated SENSEX candidate is selected; SENSEX remains fully journaled and is labelled **observation only** in the dashboard. Its records are tagged separately from older/legacy paper records, so the 10-day forward report begins cleanly. The model records the observed tick separately from the simulated fill: Target 1 winners are credited at Target 1 rather than a more favourable tick beyond it; stop losses use the observed worse price if it gaps through the stop. Time exits are shown separately and excluded from the win-rate denominator.

It never sends an order. The **Reports** page shows observed sessions, forward-policy closed-trade counts, resolved win rate, time exits, P/L per lot, average R and market split. Do not optimise from a few outcomes: retain a hold-out sample and alter one small weight group at a time.

### 300-day Kite core backtest

Run a historical, no-look-ahead replay from the project folder:

```powershell
python -m nice_pro.backtest.runner --underlying NIFTY --days 300 --optimise
```

Replace `NIFTY` with `SENSEX` for a separate report. Kite minute requests are automatically split into safe 60-day chunks. The command saves a JSON performance summary, a trade-by-trade CSV, and (with `--optimise`) a small parameter-candidate report under `data/backtests/`.

This is explicitly a **Core Directional Backtest**: it validates historical 1m/5m/15m/30m/1h price-based MTF logic, score/grade gating, ATR risk, time filters, and target/stop outcomes. It cannot recreate 10s/30s timing, historical full option-chain states, Hero/Scalp logic, bid/ask depth, estimated CVD, OTM continuation, or historical option-premium P/L from Kite candles. Those remain forward-test-only fields in the live journal.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/ROADMAP.md](docs/ROADMAP.md).
