"""Cost-application test: fees + slippage move fills the right way and hit both sides of a trade."""

import pytest

from engine.backtester import run_backtest
from engine.costs import CostModel
from tests.conftest import make_ohlcv
from tests.test_known_answer import CLOSES, INITIAL, OPENS, SHARES


def test_costs_applied_on_both_fills(threshold_rules):
    slip = 0.001  # 10 bps
    fee = 0.001  # 10 bps
    df = make_ohlcv(CLOSES, OPENS)
    run = run_backtest(
        df,
        threshold_rules,
        initial_capital=INITIAL,
        cost_model=CostModel(fees_bps=10, slippage_bps=10),
        symbol="TEST",
    )

    # Independently re-derive the expected numbers from the documented formula.
    buy_fill = 102.0 * (1 + slip)  # slippage pushes the buy UP
    shares = INITIAL / (buy_fill * (1 + fee))
    entry_notional = shares * buy_fill
    entry_fee = entry_notional * fee
    cash_after_entry = INITIAL - entry_notional - entry_fee

    sell_fill = 97.0 * (1 - slip)  # slippage pushes the sell DOWN
    exit_notional = shares * sell_fill
    exit_fee = exit_notional * fee
    expected_final = cash_after_entry + exit_notional - exit_fee

    trade = run.trades[0]
    assert trade["entry_px"] == pytest.approx(buy_fill)
    assert trade["exit_px"] == pytest.approx(sell_fill)
    assert trade["fees"] == pytest.approx(entry_fee + exit_fee)
    assert run.equity_curve.iloc[-1] == pytest.approx(expected_final)

    # Fixed-fraction = 1.0 deploys all capital at entry (notional + fee == budget).
    assert cash_after_entry == pytest.approx(0.0, abs=1e-6)


def test_costs_reduce_returns_vs_zero_cost(threshold_rules):
    df = make_ohlcv(CLOSES, OPENS)
    zero = run_backtest(df, threshold_rules, initial_capital=INITIAL, cost_model=CostModel(0, 0))
    costed = run_backtest(df, threshold_rules, initial_capital=INITIAL, cost_model=CostModel(5, 5))
    # Same trade, but costs must make the realized outcome strictly worse.
    assert costed.equity_curve.iloc[-1] < zero.equity_curve.iloc[-1]
    assert zero.equity_curve.iloc[-1] == pytest.approx(SHARES * 97)
