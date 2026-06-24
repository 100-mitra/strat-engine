# Data fixtures

Small, committed daily OHLCV CSVs so backtests run reproducibly with **no network access**.

| File          | Symbol  | Source        | Range                    | Bars |
|---------------|---------|---------------|--------------------------|------|
| `SPY.csv`     | SPY     | Yahoo Finance | 2019-01-02 → 2023-12-29  | 1258 |
| `BTC-USD.csv` | BTC-USD | Yahoo Finance | 2019-01-01 → 2023-12-31  | 1826 |

Snapshot taken 2026-06-24. Regenerate with `python scripts/fetch_fixtures.py`.

## Schema

One row per daily bar, ascending by date:

```
date,open,high,low,close,volume
2019-01-02,245.979996,251.210007,245.949997,250.179993,126925200
```

`date` is `YYYY-MM-DD`; prices are floats; `volume` is an integer.

## Known limitations (read this)

- **Unadjusted prices.** OHLC is *not* adjusted for dividends or splits (`auto_adjust=False`).
  Dividend ex-dates therefore show as small overnight gaps. SPY has no splits in this window and
  BTC-USD never splits, so the series are continuous, but total-return performance is understated
  for SPY by the dividend yield. A production system would offer an adjusted-close `DataSource`.
- **Survivorship bias.** The MVP uses a fixed, currently-liquid universe (SPY, BTC-USD). It does not
  model delisted/failed instruments, so backtests on a broader universe would be optimistic.
  Delisting-inclusive data is a documented stretch goal.
- **Single-symbol backtests.** Phase 1 runs one symbol per backtest; the data model stores a
  `universe` list for a future multi-symbol extension.

These caveats are restated in the top-level README's "Limitations" section.
