"""THE headline test: no look-ahead bias via a truncation invariant.

Running the engine on ``data[:T]`` must produce signal, position, and equity series for every bar
``t < T`` that are *identical* to running on the full dataset. If any future bar could change a
past signal or fill, this fails. We test multiple random cutoffs against real SPY data with a
strategy that uses indicator warmup (RSI + SMA trend filter), where look-ahead bugs love to hide.
"""

import random

import numpy as np

from engine.backtester import run_backtest

WARMUP = 60  # past RSI(14)/SMA(50) warmup
SEED = 20260624


def _run(df, rules):
    return run_backtest(df, rules, initial_capital=100_000.0)


def test_truncation_invariant_signals_positions_equity(spy, rsi_trend_rules):
    df = spy
    full = _run(df, rsi_trend_rules)

    rng = random.Random(SEED)
    cutoffs = sorted(rng.sample(range(WARMUP, len(df)), 10))

    for t in cutoffs:
        trunc = _run(df.iloc[:t], rsi_trend_rules)
        overlap = slice(0, t)

        assert np.array_equal(
            trunc.entry_signal.to_numpy(), full.entry_signal.iloc[overlap].to_numpy()
        ), f"entry signal changed by future data at cutoff {t}"
        assert np.array_equal(
            trunc.exit_signal.to_numpy(), full.exit_signal.iloc[overlap].to_numpy()
        ), f"exit signal changed by future data at cutoff {t}"
        assert np.array_equal(
            trunc.position.to_numpy(), full.position.iloc[overlap].to_numpy()
        ), f"position changed by future data at cutoff {t}"
        assert np.allclose(
            trunc.equity_curve.to_numpy(),
            full.equity_curve.iloc[overlap].to_numpy(),
            rtol=0,
            atol=1e-9,
        ), f"equity changed by future data at cutoff {t}"


def test_truncation_invariant_holds_for_threshold_strategy(spy, threshold_rules):
    # A second, indicator-free strategy to isolate execution-timing look-ahead from indicator causality.
    df = spy
    full = _run(df, threshold_rules)
    for t in (80, 200, 333, 470):
        trunc = _run(df.iloc[:t], threshold_rules)
        assert np.array_equal(trunc.position.to_numpy(), full.position.iloc[:t].to_numpy())
        assert np.allclose(
            trunc.equity_curve.to_numpy(), full.equity_curve.iloc[:t].to_numpy(), atol=1e-9
        )
