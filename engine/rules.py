"""Rule grammar: operands, operators, and AND/OR evaluation.

A strategy's ``rules`` JSON has an ``entry`` and an ``exit`` group; each group is a flat list of
conditions combined by a single ``logic`` of ``AND`` or ``OR`` (one combinator per group avoids
ambiguous mixed-precedence). A condition is ``{left, operator, right}`` where each operand is one
of ``indicator`` / ``price`` / ``value``.

Look-ahead safety: every operand is causal (indicators use data <= t; ``crosses_*`` uses only t-1
and t). Any NaN operand (e.g. an indicator still in warmup) makes the condition False, so no trade
fires until all referenced indicators are defined.
"""

from __future__ import annotations

import pandas as pd

from engine.indicators import PRICE_FIELDS, compute_indicator

LOGIC_OPS = ("AND", "OR")


class RuleError(Exception):
    """Raised for a malformed operand, operator, or rule group."""


# ---------------------------------------------------------------------------
# Operands
# ---------------------------------------------------------------------------
def evaluate_operand(operand: dict, df: pd.DataFrame) -> pd.Series:
    if not isinstance(operand, dict):
        raise RuleError(f"operand must be an object, got {type(operand).__name__}")
    otype = operand.get("type")

    if otype == "indicator":
        return compute_indicator(
            operand.get("name"), df, operand.get("params", {}), operand.get("on", "close")
        )
    if otype == "price":
        field = operand.get("field")
        if field not in PRICE_FIELDS:
            raise RuleError(f"invalid price field {field!r}; expected one of {PRICE_FIELDS}")
        return df[field]
    if otype == "value":
        value = operand.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuleError(f"value operand must be numeric, got {value!r}")
        return pd.Series(float(value), index=df.index)

    raise RuleError(f"unknown operand type {otype!r}")


def is_constant_operand(operand: dict) -> bool:
    return isinstance(operand, dict) and operand.get("type") == "value"


# ---------------------------------------------------------------------------
# Operators (NaN-safe: comparisons against NaN yield False)
# ---------------------------------------------------------------------------
def _gt(left: pd.Series, right: pd.Series) -> pd.Series:
    return (left > right).fillna(False)


def _lt(left: pd.Series, right: pd.Series) -> pd.Series:
    return (left < right).fillna(False)


def _ge(left: pd.Series, right: pd.Series) -> pd.Series:
    return (left >= right).fillna(False)


def _le(left: pd.Series, right: pd.Series) -> pd.Series:
    return (left <= right).fillna(False)


def _crosses_above(left: pd.Series, right: pd.Series) -> pd.Series:
    # left was at/below right on the previous bar and is strictly above on this bar.
    prev = left.shift(1) <= right.shift(1)
    now = left > right
    return (prev & now).fillna(False)


def _crosses_below(left: pd.Series, right: pd.Series) -> pd.Series:
    prev = left.shift(1) >= right.shift(1)
    now = left < right
    return (prev & now).fillna(False)


OPERATOR_REGISTRY = {
    ">": _gt,
    "<": _lt,
    ">=": _ge,
    "<=": _le,
    "crosses_above": _crosses_above,
    "crosses_below": _crosses_below,
}


def available_operators() -> list[str]:
    return list(OPERATOR_REGISTRY)


# ---------------------------------------------------------------------------
# Conditions & rule groups
# ---------------------------------------------------------------------------
def evaluate_condition(condition: dict, df: pd.DataFrame) -> pd.Series:
    if not isinstance(condition, dict):
        raise RuleError("condition must be an object")
    operator = condition.get("operator")
    op = OPERATOR_REGISTRY.get(operator)
    if op is None:
        raise RuleError(f"unknown operator {operator!r}; available: {', '.join(OPERATOR_REGISTRY)}")
    left = evaluate_operand(condition.get("left"), df)
    right = evaluate_operand(condition.get("right"), df)
    return op(left, right).astype(bool)


def evaluate_rule_group(group: dict, df: pd.DataFrame) -> pd.Series:
    if not isinstance(group, dict):
        raise RuleError("rule group must be an object")
    conditions = group.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise RuleError("rule group requires a non-empty 'conditions' list")
    logic = str(group.get("logic", "AND")).upper()
    if logic not in LOGIC_OPS:
        raise RuleError(f"logic must be one of {LOGIC_OPS}, got {group.get('logic')!r}")

    result = evaluate_condition(conditions[0], df)
    for condition in conditions[1:]:
        nxt = evaluate_condition(condition, df)
        result = (result & nxt) if logic == "AND" else (result | nxt)
    return result.astype(bool)


def evaluate_rules(rules: dict, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return (entry_signal, exit_signal) boolean series aligned to ``df.index``."""
    if not isinstance(rules, dict) or "entry" not in rules or "exit" not in rules:
        raise RuleError("rules must be an object with 'entry' and 'exit' groups")
    entry = evaluate_rule_group(rules["entry"], df)
    exit_ = evaluate_rule_group(rules["exit"], df)
    return entry, exit_
