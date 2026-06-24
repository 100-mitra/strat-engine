"""Regenerate the committed OHLCV CSV fixtures from Yahoo Finance.

The CSVs under ``data/`` are committed so backtests are reproducible without network access. This
script documents exactly how they were produced and lets anyone regenerate them.

Usage:
    python scripts/fetch_fixtures.py

Output schema (one row per daily bar, ascending by date):
    date,open,high,low,close,volume

Notes:
- Unadjusted OHLC is used (auto_adjust=False). See data/README.md for the implications.
- A fixed end date keeps the fixture a static snapshot.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# symbol -> (yahoo ticker, start, end)  — end is exclusive in yfinance.
FIXTURES = {
    "SPY": ("SPY", "2019-01-01", "2024-01-01"),
    "BTC-USD": ("BTC-USD", "2019-01-01", "2024-01-01"),
}


def fetch_one(ticker: str, start: str, end: str) -> pd.DataFrame:
    raw = yf.download(
        ticker, start=start, end=end, interval="1d", progress=False, auto_adjust=False
    )
    if raw.empty:
        raise RuntimeError(f"No data returned for {ticker}")
    # Newer yfinance returns a (Price, Ticker) column MultiIndex for a single symbol; flatten it.
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    df.index.name = "date"
    df = df.dropna().sort_index()
    df["volume"] = df["volume"].astype("int64")
    return df.round(6)


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for symbol, (ticker, start, end) in FIXTURES.items():
        df = fetch_one(ticker, start, end)
        out = DATA_DIR / f"{symbol}.csv"
        df.to_csv(out, date_format="%Y-%m-%d")
        print(f"wrote {out}  ({len(df)} rows, {df.index.min().date()} -> {df.index.max().date()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
