"""Strict validation of the rule grammar, surfaced as descriptive DRF 400s.

Allowed indicators, operators, and price fields come straight from the engine registries, so the
API never hard-codes a strategy vocabulary that could drift from the engine. Each failure names the
offending path (e.g. ``entry.conditions[1].left``) so clients can fix input precisely.
"""

from __future__ import annotations

from rest_framework import serializers

from engine.indicators import INDICATOR_REGISTRY, PRICE_FIELDS
from engine.rules import LOGIC_OPS, OPERATOR_REGISTRY

INDICATOR_NAMES = set(INDICATOR_REGISTRY)
OPERATORS = set(OPERATOR_REGISTRY)


def _err(msg: str):
    raise serializers.ValidationError(msg)


def _validate_operand(operand, path: str) -> bool:
    """Validate one operand; return True if it is a constant (``value``) operand."""
    if not isinstance(operand, dict):
        _err(f"{path}: operand must be an object")
    otype = operand.get("type")

    if otype == "indicator":
        extra = set(operand) - {"type", "name", "params", "on"}
        if extra:
            _err(f"{path}: unexpected indicator fields {sorted(extra)}")
        name = operand.get("name")
        if not isinstance(name, str) or name.upper() not in INDICATOR_NAMES:
            _err(f"{path}: unknown indicator {name!r}; available {sorted(INDICATOR_NAMES)}")
        params = operand.get("params", {})
        if not isinstance(params, dict):
            _err(f"{path}: params must be an object")
        window = params.get("window")
        if isinstance(window, bool) or not isinstance(window, int):
            _err(f"{path}: params.window must be an integer")
        if window < 1:
            _err(f"{path}: params.window must be >= 1")
        on = operand.get("on", "close")
        if on not in PRICE_FIELDS:
            _err(f"{path}: 'on' must be one of {list(PRICE_FIELDS)}")
        return False

    if otype == "price":
        extra = set(operand) - {"type", "field"}
        if extra:
            _err(f"{path}: unexpected price fields {sorted(extra)}")
        if operand.get("field") not in PRICE_FIELDS:
            _err(f"{path}: price.field must be one of {list(PRICE_FIELDS)}")
        return False

    if otype == "value":
        extra = set(operand) - {"type", "value"}
        if extra:
            _err(f"{path}: unexpected value fields {sorted(extra)}")
        value = operand.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            _err(f"{path}: value must be numeric")
        return True

    _err(f"{path}: operand.type must be one of indicator/price/value, got {otype!r}")


def _validate_condition(condition, path: str) -> None:
    if not isinstance(condition, dict):
        _err(f"{path}: condition must be an object")
    extra = set(condition) - {"left", "operator", "right"}
    if extra:
        _err(f"{path}: unexpected condition fields {sorted(extra)}")
    for key in ("left", "operator", "right"):
        if key not in condition:
            _err(f"{path}: missing '{key}'")
    if condition["operator"] not in OPERATORS:
        _err(f"{path}: unknown operator {condition['operator']!r}; available {sorted(OPERATORS)}")
    left_const = _validate_operand(condition["left"], f"{path}.left")
    right_const = _validate_operand(condition["right"], f"{path}.right")
    if left_const and right_const:
        _err(f"{path}: at least one operand must be a price or indicator (not value vs value)")


def _validate_group(group, path: str) -> None:
    if not isinstance(group, dict):
        _err(f"{path}: must be an object")
    extra = set(group) - {"logic", "conditions"}
    if extra:
        _err(f"{path}: unexpected fields {sorted(extra)}")
    if str(group.get("logic", "AND")).upper() not in LOGIC_OPS:
        _err(f"{path}.logic must be one of {list(LOGIC_OPS)}")
    conditions = group.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        _err(f"{path}.conditions must be a non-empty list")
    for i, condition in enumerate(conditions):
        _validate_condition(condition, f"{path}.conditions[{i}]")


def validate_rules(rules):
    if not isinstance(rules, dict):
        _err("rules must be an object with 'entry' and 'exit' groups")
    extra = set(rules) - {"entry", "exit"}
    if extra:
        _err(f"rules: unexpected groups {sorted(extra)}; expected 'entry' and 'exit'")
    for key in ("entry", "exit"):
        if key not in rules:
            _err(f"rules: missing '{key}' group")
        _validate_group(rules[key], key)
    return rules


def validate_position_sizing(position_sizing):
    if not isinstance(position_sizing, dict):
        _err("position_sizing must be an object")
    if position_sizing.get("type") != "fixed_fraction":
        _err("position_sizing.type must be 'fixed_fraction'")
    fraction = position_sizing.get("fraction", 1.0)
    if isinstance(fraction, bool) or not isinstance(fraction, (int, float)):
        _err("position_sizing.fraction must be numeric")
    if not 0 < fraction <= 1:
        _err("position_sizing.fraction must be in (0, 1]")
    return position_sizing


def validate_universe(universe, available_symbols):
    if not isinstance(universe, list) or not universe:
        _err("universe must be a non-empty list of symbols")
    if not all(isinstance(s, str) for s in universe):
        _err("universe symbols must be strings")
    unknown = [s for s in universe if s not in available_symbols]
    if unknown:
        _err(f"unknown symbols {unknown}; available {sorted(available_symbols)}")
    return universe
