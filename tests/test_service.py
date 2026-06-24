"""Engine orchestration: reproducibility hash, determinism, metrics, OOS split, tearsheet."""

import copy

import pytest

from engine.datasource import CSVDataSource
from engine.metrics import generate_tearsheet_html
from engine.service import BacktestSpecError, execute_backtest, position_fraction_from_sizing


def _snapshot(rules):
    return {
        "name": "demo",
        "rules": rules,
        "universe": ["SPY"],
        "position_sizing": {"type": "fixed_fraction", "fraction": 1.0},
        "version": 1,
    }


def _params(**overrides):
    base = {
        "symbol": "SPY",
        "start": "2019-01-01",
        "end": "2021-12-31",
        "initial_capital": 100_000.0,
        "fees_bps": 5,
        "slippage_bps": 5,
        "oos_split_date": None,
        "periods_per_year": 252,
    }
    base.update(overrides)
    return base


def test_same_inputs_same_hash(data_dir, rsi_trend_rules):
    src = CSVDataSource(data_dir)
    snap = _snapshot(rsi_trend_rules)
    a = execute_backtest(src, snap, _params())
    b = execute_backtest(src, copy.deepcopy(snap), _params())
    assert a.result_hash == b.result_hash
    # Determinism: not just the hash — the actual equity curve must be identical.
    assert a.equity_curve == b.equity_curve


def test_different_params_change_hash(data_dir, rsi_trend_rules):
    src = CSVDataSource(data_dir)
    snap = _snapshot(rsi_trend_rules)
    base = execute_backtest(src, snap, _params())
    higher_fees = execute_backtest(src, snap, _params(fees_bps=25))
    assert base.result_hash != higher_fees.result_hash


def test_different_strategy_changes_hash(data_dir, rsi_trend_rules, threshold_rules):
    src = CSVDataSource(data_dir)
    a = execute_backtest(src, _snapshot(rsi_trend_rules), _params())
    b = execute_backtest(src, _snapshot(threshold_rules), _params())
    assert a.result_hash != b.result_hash


def test_metrics_shape(data_dir, rsi_trend_rules):
    src = CSVDataSource(data_dir)
    out = execute_backtest(src, _snapshot(rsi_trend_rules), _params())
    for key in ("cagr", "sharpe", "sortino", "max_drawdown", "win_rate", "num_trades"):
        assert key in out.metrics
    assert out.metrics["periods_per_year"] == 252
    assert out.bars > 0


def test_oos_split_reported_separately(data_dir, rsi_trend_rules):
    src = CSVDataSource(data_dir)
    out = execute_backtest(src, _snapshot(rsi_trend_rules), _params(oos_split_date="2020-06-01"))
    assert "oos" in out.metrics
    assert "in_sample" in out.metrics["oos"]
    assert "out_of_sample" in out.metrics["oos"]
    # Equity points carry a region tag matching the split.
    regions = {p["region"] for p in out.equity_curve}
    assert regions == {"in_sample", "out_of_sample"}


def test_tearsheet_is_html(data_dir, rsi_trend_rules):
    src = CSVDataSource(data_dir)
    out = execute_backtest(src, _snapshot(rsi_trend_rules), _params())
    # Reconstruct returns from the equity points to render a tearsheet.
    import pandas as pd

    eq = pd.Series(
        [p["equity"] for p in out.equity_curve],
        index=pd.to_datetime([p["date"] for p in out.equity_curve]),
    )
    html = generate_tearsheet_html(eq.pct_change().fillna(0.0), title="Test")
    assert "<html" in html.lower()
    assert len(html) > 1000


def test_position_fraction_resolution():
    assert position_fraction_from_sizing(None) == 1.0
    assert position_fraction_from_sizing({"type": "fixed_fraction", "fraction": 0.25}) == 0.25
    with pytest.raises(BacktestSpecError):
        position_fraction_from_sizing({"type": "kelly"})
    with pytest.raises(BacktestSpecError):
        position_fraction_from_sizing({"type": "fixed_fraction", "fraction": 0})
