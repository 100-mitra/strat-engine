"""Rule-engine semantics: operators, crosses_* timing, NaN handling, AND/OR, error cases."""

import numpy as np
import pandas as pd
import pytest

from engine.indicators import IndicatorError
from engine.rules import RuleError, evaluate_condition, evaluate_rule_group
from tests.conftest import make_ohlcv


def _cond(left, op, right):
    return {"left": left, "operator": op, "right": right}


PRICE_CLOSE = {"type": "price", "field": "close"}


def test_crosses_above_fires_on_the_crossing_bar():
    # close vs constant 100: below, below, above, above -> cross at index 2 only.
    df = make_ohlcv([98, 99, 101, 102])
    res = evaluate_condition(
        _cond(PRICE_CLOSE, "crosses_above", {"type": "value", "value": 100}), df
    )
    assert res.to_list() == [False, False, True, False]


def test_crosses_below_fires_on_the_crossing_bar():
    df = make_ohlcv([102, 101, 99, 98])
    res = evaluate_condition(
        _cond(PRICE_CLOSE, "crosses_below", {"type": "value", "value": 100}), df
    )
    assert res.to_list() == [False, False, True, False]


def test_crosses_above_first_bar_is_false():
    # No previous bar at t0 -> never a cross on the first bar.
    df = make_ohlcv([200, 100])
    res = evaluate_condition(
        _cond(PRICE_CLOSE, "crosses_above", {"type": "value", "value": 100}), df
    )
    assert res.iloc[0] is np.False_ or res.iloc[0] == False  # noqa: E712


def test_nan_operand_makes_condition_false():
    # SMA(5) is NaN for the first 4 bars; "close > SMA(5)" must be False there, not error.
    df = make_ohlcv([10, 11, 12, 13, 14, 15, 16])
    cond = _cond(PRICE_CLOSE, ">", {"type": "indicator", "name": "SMA", "params": {"window": 5}})
    res = evaluate_condition(cond, df)
    assert res.iloc[:4].any() == False  # noqa: E712 -- warmup region is all False
    assert res.dtype == bool


def test_and_or_logic():
    df = make_ohlcv([105, 95])
    gt = _cond(PRICE_CLOSE, ">", {"type": "value", "value": 100})
    lt = _cond(PRICE_CLOSE, "<", {"type": "value", "value": 100})
    and_group = {"logic": "AND", "conditions": [gt, lt]}
    or_group = {"logic": "OR", "conditions": [gt, lt]}
    assert evaluate_rule_group(and_group, df).to_list() == [False, False]
    assert evaluate_rule_group(or_group, df).to_list() == [True, True]


def test_value_operand_numeric_only():
    df = make_ohlcv([1, 2])
    with pytest.raises(RuleError):
        evaluate_condition(_cond(PRICE_CLOSE, ">", {"type": "value", "value": "nope"}), df)


def test_unknown_operator_raises():
    df = make_ohlcv([1, 2])
    with pytest.raises(RuleError):
        evaluate_condition(_cond(PRICE_CLOSE, "≈", {"type": "value", "value": 1}), df)


def test_unknown_indicator_raises():
    df = make_ohlcv([1, 2, 3])
    with pytest.raises(IndicatorError):
        evaluate_condition(
            _cond(
                {"type": "indicator", "name": "BOLLINGER", "params": {"window": 2}},
                ">",
                PRICE_CLOSE,
            ),
            df,
        )


def test_bad_price_field_raises():
    df = make_ohlcv([1, 2, 3])
    with pytest.raises(RuleError):
        evaluate_condition(_cond({"type": "price", "field": "bid"}, ">", PRICE_CLOSE), df)


def test_empty_conditions_raises():
    df = make_ohlcv([1, 2])
    with pytest.raises(RuleError):
        evaluate_rule_group({"logic": "AND", "conditions": []}, df)


def test_crosses_against_constant_is_allowed():
    # RSI-style "crosses above a threshold" is a legitimate, common signal — not an error.
    df = make_ohlcv([90, 95, 105, 110])
    res = evaluate_condition(
        _cond(PRICE_CLOSE, "crosses_above", {"type": "value", "value": 100}), df
    )
    assert isinstance(res, pd.Series) and res.to_list() == [False, False, True, False]
