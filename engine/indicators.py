"""Indicator registry over the ``ta`` library.

Indicators are looked up by name in ``INDICATOR_REGISTRY`` — there are no hard-coded indicator
branches in the rule engine or the API. Each indicator is **causal**: the value at bar *t* depends
only on bars up to and including *t* (proven by ``tests/test_indicators_causal.py``). Warmup bars
are left as NaN (``fillna=False``); the rule evaluator treats NaN operands as a failed condition.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, EMAIndicator, SMAIndicator
from ta.volatility import AverageTrueRange

PRICE_FIELDS = ("open", "high", "low", "close", "volume")


class IndicatorError(Exception):
    """Raised for an unknown indicator, bad params, or a bad price field."""


def _series(df: pd.DataFrame, on: str) -> pd.Series:
    if on not in PRICE_FIELDS:
        raise IndicatorError(f"invalid price field {on!r}; expected one of {PRICE_FIELDS}")
    return df[on]


def _window(params: dict) -> int:
    if "window" not in params:
        raise IndicatorError("missing required param 'window'")
    window = params["window"]
    if isinstance(window, bool) or not isinstance(window, int):
        raise IndicatorError(f"'window' must be an integer, got {window!r}")
    if window < 1:
        raise IndicatorError(f"'window' must be >= 1, got {window}")
    return window


def _sma(df, params, on="close") -> pd.Series:
    return SMAIndicator(_series(df, on), window=_window(params), fillna=False).sma_indicator()


def _ema(df, params, on="close") -> pd.Series:
    return EMAIndicator(_series(df, on), window=_window(params), fillna=False).ema_indicator()


def _rsi(df, params, on="close") -> pd.Series:
    return RSIIndicator(_series(df, on), window=_window(params), fillna=False).rsi()


def _adx(df, params, on="close") -> pd.Series:
    # ADX is computed from high/low/close; the `on` field is not applicable.
    return ADXIndicator(
        df["high"], df["low"], df["close"], window=_window(params), fillna=False
    ).adx()


def _atr(df, params, on="close") -> pd.Series:
    # ATR is computed from high/low/close; the `on` field is not applicable.
    return AverageTrueRange(
        df["high"], df["low"], df["close"], window=_window(params), fillna=False
    ).average_true_range()


@dataclass(frozen=True)
class IndicatorSpec:
    name: str
    func: Callable[..., pd.Series]
    uses_price_field: bool  # whether the operand's `on` field is meaningful


INDICATOR_REGISTRY: dict[str, IndicatorSpec] = {
    "SMA": IndicatorSpec("SMA", _sma, uses_price_field=True),
    "EMA": IndicatorSpec("EMA", _ema, uses_price_field=True),
    "RSI": IndicatorSpec("RSI", _rsi, uses_price_field=True),
    "ADX": IndicatorSpec("ADX", _adx, uses_price_field=False),
    "ATR": IndicatorSpec("ATR", _atr, uses_price_field=False),
}


def available_indicators() -> list[str]:
    return sorted(INDICATOR_REGISTRY)


def get_indicator(name: str) -> IndicatorSpec:
    spec = INDICATOR_REGISTRY.get(str(name).upper())
    if spec is None:
        raise IndicatorError(
            f"unknown indicator {name!r}; available: {', '.join(available_indicators())}"
        )
    return spec


def compute_indicator(name: str, df: pd.DataFrame, params: dict, on: str = "close") -> pd.Series:
    """Compute an indicator series aligned to ``df.index``. Raises IndicatorError on bad input."""
    spec = get_indicator(name)
    params = params or {}
    series = spec.func(df, params, on=on)
    series.name = f"{spec.name}({params.get('window')},{on})"
    return series
