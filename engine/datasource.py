"""Data access behind a swappable interface.

A ``DataSource`` yields a canonical OHLCV ``DataFrame``:

- index: a sorted, unique, tz-naive ``DatetimeIndex`` named ``date``
- columns: exactly ``open, high, low, close, volume`` (floats)

The engine depends only on this contract, so CSV fixtures, a yfinance loader, or a future broker
feed are interchangeable. ``data_snapshot_hash`` fingerprints the exact bars a run consumed and
feeds the reproducibility hash, so a change in the underlying data forces a recompute.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


class DataSourceError(Exception):
    """Raised when data cannot be loaded or fails the OHLCV contract."""


def _normalize(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Coerce a raw frame into the canonical OHLCV contract or raise DataSourceError."""
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise DataSourceError(f"{symbol}: missing columns {missing}")

    df = df[OHLCV_COLUMNS].copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        raise DataSourceError(f"{symbol}: index must be datetime")
    df.index = df.index.tz_localize(None)
    df.index.name = "date"

    for col in OHLCV_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if df.index.has_duplicates:
        raise DataSourceError(f"{symbol}: duplicate dates in data")
    df = df.sort_index()
    if df[["open", "high", "low", "close"]].isna().any().any():
        raise DataSourceError(f"{symbol}: NaN in OHLC data")
    return df


class DataSource(ABC):
    """Swappable market-data provider."""

    @abstractmethod
    def load(self, symbol: str, start=None, end=None) -> pd.DataFrame:
        """Return canonical OHLCV bars for ``symbol`` within [start, end] inclusive."""

    @staticmethod
    def _slice(df: pd.DataFrame, start, end, symbol: str) -> pd.DataFrame:
        if start is not None:
            df = df[df.index >= pd.Timestamp(start)]
        if end is not None:
            df = df[df.index <= pd.Timestamp(end)]
        if df.empty:
            raise DataSourceError(f"{symbol}: no data in range [{start}, {end}]")
        return df


class CSVDataSource(DataSource):
    """Loads ``{data_dir}/{symbol}.csv`` fixtures (the default for the MVP)."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)

    def symbols(self) -> list[str]:
        return sorted(p.stem for p in self.data_dir.glob("*.csv"))

    def load(self, symbol: str, start=None, end=None) -> pd.DataFrame:
        path = self.data_dir / f"{symbol}.csv"
        if not path.exists():
            raise DataSourceError(
                f"Unknown symbol {symbol!r}; available: {', '.join(self.symbols()) or 'none'}"
            )
        df = pd.read_csv(path, parse_dates=["date"], index_col="date")
        df = _normalize(df, symbol)
        return self._slice(df, start, end, symbol)


class YFinanceDataSource(DataSource):
    """Optional live loader behind the same interface. Network-dependent, so it is never used by
    the test suite or CI — the CSV fixtures are the deterministic default."""

    def load(self, symbol: str, start=None, end=None) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover - optional dependency path
            raise DataSourceError("yfinance is not installed") from exc

        raw = yf.download(
            symbol, start=start, end=end, interval="1d", progress=False, auto_adjust=False
        )
        if raw.empty:
            raise DataSourceError(f"{symbol}: no data returned from yfinance")
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.rename(columns=str.lower)
        return _normalize(raw, symbol)


def data_snapshot_hash(df: pd.DataFrame) -> str:
    """Deterministic fingerprint of the exact OHLCV bars used in a run.

    Canonicalizes columns and date format so the same bars always hash identically across
    processes; any change to the data (different range, corrected price) changes the hash.
    """
    canonical = df[OHLCV_COLUMNS].to_csv(date_format="%Y-%m-%dT%H:%M:%S")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
