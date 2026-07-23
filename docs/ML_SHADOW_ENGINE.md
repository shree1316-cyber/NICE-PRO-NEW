# ML Shadow Engine

This is a paper-only research layer. It does not submit broker orders and does
not replace the `NIFTY_CORE_308D_V1` paper-forward policy.

## Initial historical inputs

The first training dataset uses only values reproducible from completed Kite
one-minute candles: trend (EMA/VWAP/returns), momentum (RSI/returns), volatility
(ATR), levels (opening range), futures-volume proxy, time of session, and four
deterministic regimes: trend up, trend down, range, and volatile expansion.

Historical option-chain, depth, estimated CVD, Hero, and scalp fields are not
included in this first model because Kite does not supply a historical series for
them. They remain journaled for a future, separately validated live-data model.

## Target

At each completed five-minute candidate, the next minute open is the entry.
The label is `1` only when +1.5R is reached before -1R within 90 minutes and
within the same exchange session. If both levels occur in one candle, the stop
wins; timeout is `0`. This is deliberately conservative.

## Next commits

1. Strict rolling walk-forward training, calibration, and model registry.
2. Dashboard ML Shadow score/status/top reasons, then monitored weekly retraining
   and three-cycle feature-pruning reports.
