"""Regression tests for the correctness bugs found in the adversarial metrics review.

Covers:
- CAGR computed directly (not via quantstats' calendar-day / trading-day mismatch).
- The undefined first-bar return is dropped, not zero-filled, before risk metrics.
- In/out-of-sample metrics derive from each segment's own equity sub-series (no boundary leak).
"""

import numpy as np
import pandas as pd
import pytest
import quantstats_lumi as qs

from engine.metrics import compute_metrics, compute_split_metrics


def _equity(values, start="2020-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="B")
    return pd.Series(np.asarray(values, dtype="float64"), index=idx)


# --- CAGR ---------------------------------------------------------------------
def test_cagr_equals_total_return_over_one_year_of_bars():
    # 252 return periods == exactly one year, so CAGR must equal total_return.
    eq = _equity(100_000 * (1.001 ** np.arange(253)))  # 253 points -> 252 returns
    m = compute_metrics(eq, [], periods_per_year=252)
    assert m["cagr"] == pytest.approx(m["total_return"], rel=1e-9)
    assert m["cagr"] == pytest.approx(1.001**252 - 1, rel=1e-9)
    # The old quantstats-based path (calendar days / 252) understates it materially.
    buggy = qs.stats.cagr(eq.pct_change().dropna(), periods=252)
    assert m["cagr"] - buggy > 0.05  # the bug understated CAGR by a large margin


def test_cagr_is_horizon_stable():
    # Same constant per-bar growth over 1y vs 2y must yield the same annualized CAGR.
    one_year = compute_metrics(
        _equity(100_000 * (1.001 ** np.arange(253))), [], periods_per_year=252
    )
    two_year = compute_metrics(
        _equity(100_000 * (1.001 ** np.arange(505))), [], periods_per_year=252
    )
    assert two_year["cagr"] == pytest.approx(one_year["cagr"], rel=1e-9)
    # total_return, by contrast, compounds with the longer horizon.
    assert two_year["total_return"] > one_year["total_return"]


# --- phantom first-bar return -------------------------------------------------
def test_sharpe_excludes_phantom_first_bar_zero():
    rng = np.random.default_rng(0)
    rets = rng.normal(0.0005, 0.01, 260)
    eq = _equity(100_000 * np.cumprod(1 + rets))
    m = compute_metrics(eq, [], periods_per_year=252)

    dropna_sharpe = qs.stats.sharpe(eq.pct_change().dropna(), periods=252)
    fillna_sharpe = qs.stats.sharpe(eq.pct_change().fillna(0.0), periods=252)
    # Metrics must match the dropna (correct) version, not the phantom-0 version.
    assert m["sharpe"] == pytest.approx(dropna_sharpe, rel=1e-9)
    assert abs(m["sharpe"] - fillna_sharpe) > 1e-6


# --- OOS boundary leak --------------------------------------------------------
def test_oos_segments_have_no_boundary_leak():
    # Flat in-sample, a +10% jump exactly on the first OOS bar, then flat.
    eq = _equity([100, 100, 100, 110, 110, 110])
    split = eq.index[2]  # last in-sample bar
    res = compute_split_metrics(eq, [], split, periods_per_year=252)

    # The boundary +10% belongs to NEITHER segment: both are internally flat.
    assert res["in_sample"]["total_return"] == pytest.approx(0.0)
    assert res["out_of_sample"]["total_return"] == pytest.approx(0.0)
    assert res["in_sample"]["volatility"] == pytest.approx(0.0)
    assert res["out_of_sample"]["volatility"] == pytest.approx(0.0)


def test_oos_returns_reconcile_with_total_return():
    rng = np.random.default_rng(7)
    eq = _equity(100_000 * np.cumprod(1 + rng.normal(0.0004, 0.012, 300)))
    split = eq.index[180]
    res = compute_split_metrics(eq, [], split, periods_per_year=252)

    out_eq = eq[eq.index > split]
    compounded = float((1 + out_eq.pct_change().dropna()).prod()) - 1
    # Each segment's compounded returns must reconcile with its reported total_return.
    assert res["out_of_sample"]["total_return"] == pytest.approx(compounded, rel=1e-9)
