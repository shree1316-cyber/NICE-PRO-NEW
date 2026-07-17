# Run NICE-PRO on Windows

## 1. Open the project folder in VS Code

Open the terminal in the `NICE-PRO-NEW` folder. The commands below work in PowerShell.

## 2. Create the local Python environment

```powershell
py -3.11 -m venv .venv
```

If `py -3.11` is unavailable, use your installed Python command instead:

```powershell
python -m venv .venv
```

## 3. Install NICE-PRO

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools
.\.venv\Scripts\python.exe -m pip install -e . --no-build-isolation
```

The first command can take several minutes because PySide6 and Kite Connect are downloaded.

## 4. Configure offline or live mode

Copy `.env.example` to `.env` in the project root.

- Leave the Kite fields blank to start the dashboard in offline mode.
- For live data, enter `KITE_API_KEY`, `KITE_API_SECRET`, and the daily `KITE_ACCESS_TOKEN` obtained through Zerodha's supported login flow.
- Keep `NICE_PAPER_TRADING_ONLY=true`.
- Do not share or commit the `.env` file.

Before a live session, confirm `NICE_SUBSCRIPTIONS` tokens against Kite's latest instrument master. Index and derivative tokens can change.

## 5. Run the dashboard

```powershell
.\.venv\Scripts\python.exe -m nice_pro
```

Expected offline result: the NICE-PRO desktop window opens with cards for NIFTY, SENSEX, market structure, options, and conviction. It shows that Kite credentials are not configured.

Expected live result: after valid credentials and a live market are available, it connects to Kite, warms recent one-minute history, discovers a narrow ATM option universe, and updates the cards. It never submits an order.

## 6. Verify the code

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
```

## Troubleshooting

- **`No module named kiteconnect` or `loguru`:** repeat the install command from step 3.
- **Dashboard opens but has no live price:** verify the access token, trading session, subscription tokens, and Kite API entitlement.
- **No option-chain data:** wait for a spot quote, then check the instrument master and current expiry availability.
- **A plan appears:** it is paper-only. NICE-PRO has no order-placement code.
