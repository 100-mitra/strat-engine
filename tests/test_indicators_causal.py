"""Indicator causality: prove (don't assume) that every indicator is look-ahead-free.

For a causal indicator, the value at bar k computed on the prefix data[:k+1] must equal the value
at bar k computed on the full series — it cannot depend on bars after k. A non-causal smoothing
would diverge here by far more than floating-point noise. This is the per-indicator complement to
the engine-level truncation invariant in test_no_lookahead.py.
"""

import numpy as np
import pandas as pd
import pytest

from engine.indicators import available_indicators, compute_indicator

CASES = [
    ("SMA", {"window": 10}),
    ("EMA", {"window": 10}),
    ("RSI", {"window": 14}),
    ("ADX", {"window": 14}),
    ("ATR", {"window": 14}),
]


@pytest.mark.parametrize("name,params", CASES)
def test_indicator_is_causal(spy, name, params):
    df = spy
    full = compute_indicator(name, df, params)
    # Sample several prefix lengths well past warmup; compare the boundary value.
    for k in range(60, len(df), 31):
        prefix_val = compute_indicator(name, df.iloc[:k], params).iloc[-1]  # bar k-1 on [0..k-1]
        full_val = full.iloc[k - 1]  # bar k-1 with the rest of history visible
        if pd.isna(prefix_val) and pd.isna(full_val):
            continue
        assert np.isclose(
            prefix_val, full_val, rtol=0, atol=1e-9
        ), f"{name} not causal at k={k}: prefix={prefix_val} full={full_val}"


def test_registry_covers_required_indicators():
    assert set(available_indicators()) >= {"SMA", "EMA", "RSI", "ADX", "ATR"}
