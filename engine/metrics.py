"""Performance metrics and the QuantStats tearsheet, wrapped defensively.

Uses ``quantstats-lumi`` (the maintained QuantStats fork) for the heavy lifting. Every metric is
guarded so a degenerate run (no trades, all-cash, zero variance) yields finite numbers instead of
NaN/inf. ``periods_per_year`` is explicit (252 for equities, 365 for 24/7 crypto) rather than
inferred, so the annualization is correct and reproducible.

Note: the *HTML tearsheet* is rendered by QuantStats, which annualizes at 252 day/yr regardless;
the numeric ``metrics`` dict below (what the API returns and tests assert on) uses the explicit
``periods_per_year``. This split is documented in the README limitations.
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


def compute_metrics(
    equity_curve: pd.Series,
    returns: pd.Series,
    trades: list[dict],
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> dict:
    """Compute the headline metrics from an equity curve, return series, and trade list."""
    initial = float(equity_curve.iloc[0])
    final = float(equity_curve.iloc[-1])

    closed = [t for t in trades if t.get("exit_px") is not None]
    wins = [t for t in closed if (t.get("pnl") or 0.0) > 0]
    win_rate = (len(wins) / len(closed)) if closed else None

    # Degenerate guard: need variation to annualize risk metrics meaningfully.
    has_variation = len(returns) > 1 and float(returns.std()) > 0

    if has_variation:
        sharpe = _finite(qs.stats.sharpe(returns, periods=periods_per_year))
        sortino = _finite(qs.stats.sortino(returns, periods=periods_per_year))
        volatility = _finite(qs.stats.volatility(returns, periods=periods_per_year))
        cagr = _finite(qs.stats.cagr(returns, periods=periods_per_year))
    else:
        sharpe = sortino = volatility = cagr = 0.0

    max_dd = _finite(qs.stats.max_drawdown(equity_curve)) if len(equity_curve) > 1 else 0.0

    return {
        "initial_equity": initial,
        "final_equity": final,
        "total_return": (final / initial - 1.0) if initial else 0.0,
        "cagr": cagr,
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
    returns: pd.Series,
    trades: list[dict],
    oos_split_date,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> dict:
    """Partition the realized series at ``oos_split_date`` and report each side separately.

    This is a *metrics partition* of one signal run, not walk-forward re-optimization (documented).
    """
    split = pd.Timestamp(oos_split_date)
    in_mask = equity_curve.index <= split
    out_mask = equity_curve.index > split

    def _trades_until(predicate):
        return [t for t in trades if t.get("entry_ts") is not None and predicate(t["entry_ts"])]

    result = {"oos_split_date": split.date().isoformat()}
    if in_mask.any():
        result["in_sample"] = compute_metrics(
            equity_curve[in_mask],
            returns[in_mask],
            _trades_until(lambda ts: pd.Timestamp(ts) <= split),
            periods_per_year,
        )
    if out_mask.any():
        result["out_of_sample"] = compute_metrics(
            equity_curve[out_mask],
            returns[out_mask],
            _trades_until(lambda ts: pd.Timestamp(ts) > split),
            periods_per_year,
        )
    return result


def generate_tearsheet_html(returns: pd.Series, title: str = "StratEngine Backtest") -> str:
    """Render a QuantStats HTML tearsheet to a string.

    Stateless: writes to a temp file, reads it back, deletes it — so it works on platforms with an
    ephemeral filesystem and never depends on persisted artifacts. Falls back to a minimal report
    if QuantStats cannot render (e.g. a no-trade run)."""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as fh:
            tmp_path = Path(fh.name)
        qs.reports.html(returns, benchmark=None, title=title, output=str(tmp_path))
        html = tmp_path.read_text(encoding="utf-8")
        tmp_path.unlink(missing_ok=True)
        return html
    except Exception as exc:  # pragma: no cover - defensive fallback for degenerate runs
        return (
            f"<html><body><h1>{title}</h1>"
            f"<p>Tearsheet could not be generated for this run ({exc}).</p>"
            f"</body></html>"
        )
