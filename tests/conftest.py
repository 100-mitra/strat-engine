"""Shared fixtures for the engine test-suite (pure, Django-free)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def data_dir() -> Path:
    return DATA_DIR


@pytest.fixture
def spy() -> pd.DataFrame:
    """Real SPY daily bars from the committed fixture (first 500 rows for speed)."""
    from engine.datasource import CSVDataSource

    return CSVDataSource(DATA_DIR).load("SPY").iloc[:500]


def make_ohlcv(closes, opens=None) -> pd.DataFrame:
    """Build a tiny OHLCV frame from explicit close (and optional open) prices."""
    closes = np.asarray(closes, dtype="float64")
    opens = np.asarray(opens, dtype="float64") if opens is not None else closes.copy()
    n = len(closes)
    index = pd.date_range("2022-01-03", periods=n, freq="B")  # business days
    highs = np.maximum(opens, closes)
    lows = np.minimum(opens, closes)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": np.full(n, 1000.0)},
        index=index,
    )


@pytest.fixture
def threshold_rules() -> dict:
    """Long when close > 100, flat when close < 100 (a simple, controllable strategy)."""
    return {
        "entry": {
            "logic": "AND",
            "conditions": [
                {
                    "left": {"type": "price", "field": "close"},
                    "operator": ">",
                    "right": {"type": "value", "value": 100},
                }
            ],
        },
        "exit": {
            "logic": "AND",
            "conditions": [
                {
                    "left": {"type": "price", "field": "close"},
                    "operator": "<",
                    "right": {"type": "value", "value": 100},
                }
            ],
        },
    }


@pytest.fixture
def rsi_trend_rules() -> dict:
    """RSI(14) oversold entry with an SMA(50) trend filter; RSI(14) > 55 exit.

    Exercises indicator warmup (NaN) and multi-condition AND logic for the look-ahead test."""
    return {
        "entry": {
            "logic": "AND",
            "conditions": [
                {
                    "left": {"type": "indicator", "name": "RSI", "params": {"window": 14}},
                    "operator": "<",
                    "right": {"type": "value", "value": 35},
                },
                {
                    "left": {"type": "price", "field": "close"},
                    "operator": ">",
                    "right": {"type": "indicator", "name": "SMA", "params": {"window": 50}},
                },
            ],
        },
        "exit": {
            "logic": "OR",
            "conditions": [
                {
                    "left": {"type": "indicator", "name": "RSI", "params": {"window": 14}},
                    "operator": ">",
                    "right": {"type": "value", "value": 55},
                }
            ],
        },
    }
