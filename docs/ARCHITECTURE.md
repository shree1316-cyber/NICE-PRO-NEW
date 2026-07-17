# NICE-PRO Architecture

## Milestone 1 flow

```text
Kite Connect service (safe skeleton)
          │
          ▼
       Event bus
          │
          ▼
      Market state
          │
          ├── Future indicator / options engines
          └── PySide6 dashboard shell
```

`src/nice_pro` is the active application package. Earlier root-level prototype files are preserved temporarily for reference and will be retired once their successor modules exist.

## Safety boundary

Milestone 1 has no order-placement code. `NICE_PAPER_TRADING_ONLY` defaults to `true`. Any future live-execution work must remain opt-in, separately tested, and disabled by default.
