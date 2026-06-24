"""Look-ahead-safe, long-only, single-symbol backtester.

Execution model (the invariant the headline test guards):

- Signals at bar *t* are computed from indicator/price data up to and including *t*.
- A signal at bar *t* is acted on at bar **t+1's open** (next-bar execution). Concretely, the fill
  loop acts at bar *t* using the signals from bar *t-1*, so no decision ever consumes its own or a
  future bar's data.
- Buys fill at ``open * (1 + slippage)``, sells at ``open * (1 - slippage)``; a fee is charged on
  each fill's notional (see :mod:`engine.costs`).
- Position sizing is fixed-fraction of current equity, in **fractional** shares.
- The equity curve is marked-to-market at each bar's close. A position still open on the final bar
  is marked-to-market (no phantom forced exit).

Signal generation is vectorized; the position/cash walk is a single forward pass because
fixed-fraction sizing is path-dependent. The forward pass never reads a future bar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from engine.costs import CostModel
from engine.rules import evaluate_rules


class BacktestError(Exception):
    """Raised for invalid backtest parameters."""


@dataclass
class BacktestRun:
    equity_curve: pd.Series  # mark-to-market portfolio value at each bar's close
    returns: pd.Series  # simple per-bar returns of the equity curve
    position: pd.Series  # shares held during each bar (0 when flat)
    entry_signal: pd.Series  # raw entry signal decided at each bar (acted on next bar)
    exit_signal: pd.Series  # raw exit signal decided at each bar (acted on next bar)
    trades: list[dict] = field(default_factory=list)
    initial_capital: float = 0.0


def run_backtest(
    df: pd.DataFrame,
    rules: dict,
    *,
    initial_capital: float = 100_000.0,
    cost_model: CostModel | None = None,
    position_fraction: float = 1.0,
    symbol: str = "ASSET",
) -> BacktestRun:
    if initial_capital <= 0:
        raise BacktestError("initial_capital must be > 0")
    if not 0 < position_fraction <= 1:
        raise BacktestError("position_fraction must be in (0, 1]")
    if df.empty:
        raise BacktestError("no data to backtest")

    cost = cost_model or CostModel()

    # --- vectorized, look-ahead-safe signal generation ---
    entry_signal, exit_signal = evaluate_rules(rules, df)

    opens = df["open"].to_numpy(dtype="float64")
    closes = df["close"].to_numpy(dtype="float64")
    index = df.index
    n = len(df)

    entry_arr = entry_signal.to_numpy(dtype=bool)
    exit_arr = exit_signal.to_numpy(dtype=bool)

    cash = float(initial_capital)
    shares = 0.0
    in_position = False
    entry_ts = None
    entry_fill = 0.0
    entry_cash_out = 0.0  # cost basis (notional + entry fee)

    equity = [0.0] * n
    pos_held = [0.0] * n
    trades: list[dict] = []

    fee_bps_factor = 1.0 + cost.fees_bps / 1e4

    for t in range(n):
        open_px = opens[t]
        # Act at bar t's open on the decision made at bar t-1 (next-bar execution).
        if t > 0:
            if in_position and exit_arr[t - 1]:
                fill = cost.sell_fill_price(open_px)
                notional = shares * fill
                fee = cost.fee(notional)
                cash += notional - fee
                proceeds = notional - fee
                trades.append(
                    {
                        "symbol": symbol,
                        "side": "long",
                        "qty": shares,
                        "entry_ts": entry_ts,
                        "entry_px": entry_fill,
                        "exit_ts": index[t],
                        "exit_px": fill,
                        "fees": entry_cash_out - (shares * entry_fill) + fee,
                        "pnl": proceeds - entry_cash_out,
                    }
                )
                shares = 0.0
                in_position = False
            elif (not in_position) and entry_arr[t - 1]:
                fill = cost.buy_fill_price(open_px)
                # Solve shares so that notional + fee == budget, with fee = notional*fees_bps/1e4.
                budget = cash * position_fraction
                shares = budget / (fill * fee_bps_factor)
                notional = shares * fill
                fee = cost.fee(notional)
                cash -= notional + fee
                in_position = True
                entry_ts = index[t]
                entry_fill = fill
                entry_cash_out = notional + fee

        pos_held[t] = shares
        equity[t] = cash + shares * closes[t]

    # A position open on the final bar is left open and marked-to-market (no forced exit).
    if in_position:
        last_close = closes[-1]
        trades.append(
            {
                "symbol": symbol,
                "side": "long",
                "qty": shares,
                "entry_ts": entry_ts,
                "entry_px": entry_fill,
                "exit_ts": None,
                "exit_px": None,
                "fees": entry_cash_out - (shares * entry_fill),
                "pnl": shares * last_close - entry_cash_out,  # unrealized
            }
        )

    equity_curve = pd.Series(equity, index=index, name="equity")
    returns = equity_curve.pct_change().fillna(0.0)
    returns.name = "returns"

    return BacktestRun(
        equity_curve=equity_curve,
        returns=returns,
        position=pd.Series(pos_held, index=index, name="position"),
        entry_signal=entry_signal,
        exit_signal=exit_signal,
        trades=trades,
        initial_capital=float(initial_capital),
    )
