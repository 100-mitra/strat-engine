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


# ---------------------------------------------------------------------------
# API fixtures (Django-backed; only used by @pytest.mark.django_db tests)
# ---------------------------------------------------------------------------
@pytest.fixture
def make_user(db):
    from django.contrib.auth.models import User

    def _make(username: str):
        return User.objects.create_user(username=username, password="pw-" + username + "-123")

    return _make


@pytest.fixture
def make_client():
    from rest_framework.authtoken.models import Token
    from rest_framework.test import APIClient

    def _make(user):
        token, _ = Token.objects.get_or_create(user=user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

    return _make


@pytest.fixture
def user(make_user):
    return make_user("alice")


@pytest.fixture
def other_user(make_user):
    return make_user("bob")


@pytest.fixture
def auth_client(make_client, user):
    return make_client(user)


@pytest.fixture
def valid_strategy_payload() -> dict:
    """A valid SMA(50) price-cross strategy on SPY (a symbol present in the fixtures)."""
    return {
        "name": "SMA50 price cross",
        "universe": ["SPY"],
        "rules": {
            "entry": {
                "logic": "AND",
                "conditions": [
                    {
                        "left": {"type": "price", "field": "close"},
                        "operator": "crosses_above",
                        "right": {"type": "indicator", "name": "SMA", "params": {"window": 50}},
                    }
                ],
            },
            "exit": {
                "logic": "AND",
                "conditions": [
                    {
                        "left": {"type": "price", "field": "close"},
                        "operator": "crosses_below",
                        "right": {"type": "indicator", "name": "SMA", "params": {"window": 50}},
                    }
                ],
            },
        },
        "position_sizing": {"type": "fixed_fraction", "fraction": 1.0},
    }


@pytest.fixture
def create_strategy(auth_client, valid_strategy_payload):
    """Create a strategy via the API and return its id."""

    def _create(**overrides):
        payload = {**valid_strategy_payload, **overrides}
        resp = auth_client.post("/api/strategies/", payload, format="json")
        assert resp.status_code == 201, resp.content
        return resp.json()["id"]

    return _create
