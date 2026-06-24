"""Engine orchestration: the single entry point the web layer calls.

``execute_backtest`` ties together data loading, the reproducibility hash, the look-ahead-safe
backtest, metrics, and the charting-ready equity series — returning plain data structures with no
Django dependency. The web layer is responsible only for persistence and caching by ``result_hash``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from engine.backtester import run_backtest
from engine.costs import DEFAULT_FEES_BPS, DEFAULT_SLIPPAGE_BPS, CostModel
from engine.datasource import DataSource, data_snapshot_hash
from engine.metrics import DEFAULT_PERIODS_PER_YEAR, compute_metrics, compute_split_metrics
from engine.reproducibility import compute_result_hash


class BacktestSpecError(Exception):
    """Raised for an invalid run spec (e.g. a bad position_sizing block)."""


@dataclass
class BacktestOutput:
    result_hash: str
    data_snapshot_hash: str
    metrics: dict
    equity_curve: list[dict]  # [{"date", "equity", "region"}] for charting
    trades: list[dict]
    bars: int = 0
    extra: dict = field(default_factory=dict)


def position_fraction_from_sizing(position_sizing: dict | None) -> float:
    """Resolve the fixed-fraction sizing block to a fraction in (0, 1]."""
    if not position_sizing:
        return 1.0
    if position_sizing.get("type") != "fixed_fraction":
        raise BacktestSpecError(f"unsupported position_sizing type {position_sizing.get('type')!r}")
    fraction = position_sizing.get("fraction", 1.0)
    if isinstance(fraction, bool) or not isinstance(fraction, (int, float)):
        raise BacktestSpecError("position_sizing.fraction must be numeric")
    if not 0 < fraction <= 1:
        raise BacktestSpecError("position_sizing.fraction must be in (0, 1]")
    return float(fraction)


def _equity_points(equity_curve: pd.Series, oos_split_date) -> list[dict]:
    split = pd.Timestamp(oos_split_date) if oos_split_date else None
    points = []
    for ts, value in equity_curve.items():
        region = "in_sample"
        if split is not None and ts > split:
            region = "out_of_sample"
        points.append({"date": ts.date().isoformat(), "equity": float(value), "region": region})
    return points


def compute_run_hash(data_source: DataSource, strategy_snapshot: dict, run_params: dict) -> str:
    """Resolve a run's ``result_hash`` without backtesting, so the API can check its cache first.

    Loads the data (to fingerprint the exact bars) but does not run the engine — cheap relative to
    a full backtest. May raise DataSourceError if the symbol/range is invalid.
    """
    df = data_source.load(run_params["symbol"], run_params.get("start"), run_params.get("end"))
    return compute_result_hash(strategy_snapshot, data_snapshot_hash(df), run_params)


def execute_backtest(
    data_source: DataSource, strategy_snapshot: dict, run_params: dict
) -> BacktestOutput:
    """Run a backtest from a frozen strategy snapshot + resolved run params.

    ``run_params`` keys: symbol, start, end, initial_capital, fees_bps, slippage_bps,
    oos_split_date, periods_per_year. The rules and sizing come from ``strategy_snapshot``.
    """
    symbol = run_params["symbol"]
    rules = strategy_snapshot["rules"]
    fraction = position_fraction_from_sizing(strategy_snapshot.get("position_sizing"))

    df = data_source.load(symbol, run_params.get("start"), run_params.get("end"))
    dsh = data_snapshot_hash(df)
    result_hash = compute_result_hash(strategy_snapshot, dsh, run_params)

    fees_bps = run_params.get("fees_bps", DEFAULT_FEES_BPS)
    slippage_bps = run_params.get("slippage_bps", DEFAULT_SLIPPAGE_BPS)
    periods = int(run_params.get("periods_per_year", DEFAULT_PERIODS_PER_YEAR))

    run = run_backtest(
        df,
        rules,
        initial_capital=float(run_params.get("initial_capital", 100_000.0)),
        cost_model=CostModel(fees_bps=fees_bps, slippage_bps=slippage_bps),
        position_fraction=fraction,
        symbol=symbol,
    )

    metrics = compute_metrics(run.equity_curve, run.trades, periods_per_year=periods)
    oos = run_params.get("oos_split_date")
    if oos:
        metrics["oos"] = compute_split_metrics(
            run.equity_curve, run.trades, oos, periods_per_year=periods
        )

    return BacktestOutput(
        result_hash=result_hash,
        data_snapshot_hash=dsh,
        metrics=metrics,
        equity_curve=_equity_points(run.equity_curve, oos),
        trades=run.trades,
        bars=len(df),
    )
