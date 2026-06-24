"""Performance metrics and the QuantStats tearsheet, wrapped defensively.

Uses ``quantstats-lumi`` (the maintained QuantStats fork) for risk ratios. Every metric is guarded
so a degenerate run (no trades, all-cash, zero variance) yields finite numbers instead of NaN/inf.
``periods_per_year`` is explicit (252 for equities, 365 for 24/7 crypto) rather than inferred.

Correctness notes (each backed by a test in ``tests/test_metrics_regression.py``):
- **CAGR is computed directly** as ``(final/initial) ** (1/years) - 1`` with ``years =
  n_return_periods / periods_per_year`` (bar-count based). We do NOT use ``qs.stats.cagr``: it
  divides *calendar* days by the *trading-day* ``periods`` divisor, which systematically understates
  CAGR for equities (~365/252). With our convention, when a window spans exactly one year of bars
  (``n_returns == periods_per_year``) CAGR equals total_return.
- **The undefined first-bar return is dropped, not forced to 0.** Returns are derived per-segment
  as ``equity.pct_change().dropna()``; a phantom leading 0 would otherwise bias Sharpe/Sortino/vol.
- **In/out-of-sample metrics are each computed from their own equity sub-series**, so the single
  boundary-crossing return belongs to neither segment and each segment's compounded returns
  reconcile exactly with its reported total_return.

The HTML tearsheet is rendered by QuantStats but is passed the same ``periods_per_year`` as the
numeric metrics, so the two artifacts annualize consistently for both equities (252) and crypto (365).
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pandas as pd
import quantstats_lumi as qs

DEFAULT_PERIODS_PER_YEAR = 252


def _finite(value, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def segment_returns(equity_curve: pd.Series) -> pd.Series:
    """Per-bar simple returns of an equity series, with the undefined first bar dropped.

    Dropping (not zero-filling) the leading bar keeps a phantom 0 out of Sharpe/Sortino/volatility,
    and makes ``prod(1 + returns) == final/initial`` for the series.
    """
    return equity_curve.pct_change().dropna()


def compute_metrics(
    equity_curve: pd.Series,
    trades: list[dict],
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> dict:
    """Compute the headline metrics from an equity curve and trade list (self-contained)."""
    initial = float(equity_curve.iloc[0])
    final = float(equity_curve.iloc[-1])
    returns = segment_returns(equity_curve)

    closed = [t for t in trades if t.get("exit_px") is not None]
    wins = [t for t in closed if (t.get("pnl") or 0.0) > 0]
    win_rate = (len(wins) / len(closed)) if closed else None

    # CAGR computed directly and unit-consistently (see module docstring).
    years = len(returns) / periods_per_year
    if years > 0 and initial > 0:
        ratio = final / initial
        cagr = ratio ** (1.0 / years) - 1.0 if ratio > 0 else -1.0
    else:
        cagr = 0.0

    # Risk metrics: need variation to annualize meaningfully.
    has_variation = len(returns) > 1 and float(returns.std()) > 0
    if has_variation:
        sharpe = _finite(qs.stats.sharpe(returns, periods=periods_per_year))
        sortino = _finite(qs.stats.sortino(returns, periods=periods_per_year))
        volatility = _finite(qs.stats.volatility(returns, periods=periods_per_year))
    else:
        sharpe = sortino = volatility = 0.0

    max_dd = _finite(qs.stats.max_drawdown(equity_curve)) if len(equity_curve) > 1 else 0.0

    return {
        "initial_equity": initial,
        "final_equity": final,
        "total_return": (final / initial - 1.0) if initial else 0.0,
        "cagr": _finite(cagr),
        "sharpe": sharpe,
        "sortino": sortino,
        "volatility": volatility,
        "max_drawdown": max_dd,
        "num_trades": len(trades),
        "num_closed_trades": len(closed),
        "win_rate": win_rate,
        "periods_per_year": periods_per_year,
    }


def compute_split_metrics(
    equity_curve: pd.Series,
    trades: list[dict],
    oos_split_date,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> dict:
    """Partition the run at ``oos_split_date`` and report each side from its OWN equity sub-series.

    A *metrics partition* of one signal run, not walk-forward re-optimization. Each segment's metrics
    are computed strictly within its own bars; the single boundary-crossing return (last in-sample
    bar -> first out-of-sample bar) belongs to neither segment, so each segment's risk metrics and
    total_return stay internally consistent.
    """
    split = pd.Timestamp(oos_split_date)
    in_eq = equity_curve[equity_curve.index <= split]
    out_eq = equity_curve[equity_curve.index > split]

    def _trades_in(predicate):
        return [
            t
            for t in trades
            if t.get("entry_ts") is not None and predicate(pd.Timestamp(t["entry_ts"]))
        ]

    result = {"oos_split_date": split.date().isoformat()}
    if len(in_eq) > 0:
        result["in_sample"] = compute_metrics(
            in_eq, _trades_in(lambda ts: ts <= split), periods_per_year
        )
    if len(out_eq) > 0:
        result["out_of_sample"] = compute_metrics(
            out_eq, _trades_in(lambda ts: ts > split), periods_per_year
        )
    return result


def generate_tearsheet_html(
    returns: pd.Series,
    title: str = "StratEngine Backtest",
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> str:
    """Render a QuantStats HTML tearsheet to a string.

    ``periods_per_year`` is forwarded so the tearsheet annualizes the same way as the numeric
    metrics. Stateless: writes to a temp file, reads it back, deletes it — so it works on platforms
    with an ephemeral filesystem and never depends on persisted artifacts. Falls back to a minimal
    report if QuantStats cannot render (e.g. a no-trade run)."""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as fh:
            tmp_path = Path(fh.name)
        qs.reports.html(
            returns,
            benchmark=None,
            title=title,
            output=str(tmp_path),
            periods_per_year=periods_per_year,
        )
        html = tmp_path.read_text(encoding="utf-8")
        tmp_path.unlink(missing_ok=True)
        return html
    except Exception as exc:  # pragma: no cover - defensive fallback for degenerate runs
        return (
            f"<html><body><h1>{title}</h1>"
            f"<p>Tearsheet could not be generated for this run ({exc}).</p>"
            f"</body></html>"
        )
