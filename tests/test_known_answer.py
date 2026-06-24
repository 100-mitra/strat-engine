"""Known-answer test: a tiny hand-built fixture with a hand-computed equity curve.

The strategy is "long while close > 100". With **zero costs** the arithmetic is fully derivable by
hand, which pins down the next-bar execution timing exactly: an entry signal at bar t must fill at
bar t+1's open, never on the signal bar itself. A look-ahead bug (filling on the signal bar) would
change equity[1] or the entry price and fail this test.
"""

import pytest

from engine.backtester import run_backtest
from engine.costs import CostModel
from tests.conftest import make_ohlcv

# Bars:  t0   t1   t2   t3   t4   t5
# close: 99  101  105  108   98   96   -> entry(close>100): F T T T F F
# open: 100  100  102  106  109   97   -> exit (close<100): T F F F T T
CLOSES = [99, 101, 105, 108, 98, 96]
OPENS = [100, 100, 102, 106, 109, 97]

INITIAL = 100_000.0
# Signal at t1 (close 101>100) -> BUY at t2 open=102. Signal at t4 (close 98<100) -> SELL at t5 open=97.
SHARES = INITIAL / 102.0  # zero-cost buy fills exactly at the open


def test_known_answer_equity_curve(threshold_rules):
    df = make_ohlcv(CLOSES, OPENS)
    run = run_backtest(
        df, threshold_rules, initial_capital=INITIAL, cost_model=CostModel(0, 0), symbol="TEST"
    )

    eq = run.equity_curve.to_list()
    # t0, t1: flat (entry only acts on the NEXT bar) -> capital unchanged. This is the anti-look-ahead anchor.
    assert eq[0] == pytest.approx(100_000.0)
    assert eq[1] == pytest.approx(100_000.0)
    # t2..t4: holding SHARES, marked at close.
    assert eq[2] == pytest.approx(SHARES * 105)
    assert eq[3] == pytest.approx(SHARES * 108)
    assert eq[4] == pytest.approx(SHARES * 98)
    # t5: sold at open 97 -> all cash.
    assert eq[5] == pytest.approx(SHARES * 97)


def test_known_answer_positions(threshold_rules):
    df = make_ohlcv(CLOSES, OPENS)
    run = run_backtest(
        df, threshold_rules, initial_capital=INITIAL, cost_model=CostModel(0, 0), symbol="TEST"
    )
    # Flat until the t2 fill, held t2..t4, flat again after the t5 exit.
    assert run.position.to_list() == pytest.approx([0, 0, SHARES, SHARES, SHARES, 0])


def test_known_answer_single_trade(threshold_rules):
    df = make_ohlcv(CLOSES, OPENS)
    run = run_backtest(
        df, threshold_rules, initial_capital=INITIAL, cost_model=CostModel(0, 0), symbol="TEST"
    )
    assert len(run.trades) == 1
    trade = run.trades[0]
    assert trade["side"] == "long"
    assert trade["entry_px"] == pytest.approx(102.0)
    assert trade["exit_px"] == pytest.approx(97.0)
    assert trade["qty"] == pytest.approx(SHARES)
    # Bought at 102, sold at 97 -> loss of 5 per share.
    assert trade["pnl"] == pytest.approx(SHARES * (97 - 102))
