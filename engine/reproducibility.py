"""Reproducibility: the content-addressed result hash.

``result_hash`` is a SHA-256 over everything that can change a backtest's output:

- ``ENGINE_VERSION`` — bumped when execution/cost math changes, so a code change invalidates stale
  cached results instead of silently serving them.
- the **frozen strategy snapshot** (rules + universe + sizing + version captured at run time),
- the **data snapshot hash** (the exact OHLCV bars consumed),
- the **resolved run params** (capital, fees, slippage, date range, OOS split, annualization).

Identical inputs ⇒ identical hash ⇒ the API can return a cached result without recomputing.
Library versions are pinned (requirements.lock), so they are not separately hashed.
"""

from __future__ import annotations

import hashlib
import json

from engine import ENGINE_VERSION


def _canonical(obj) -> str:
    # Sorted keys + str() fallback (dates, Decimals) make this stable across processes.
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def compute_result_hash(strategy_snapshot: dict, data_snapshot_hash: str, run_params: dict) -> str:
    payload = _canonical(
        {
            "engine_version": ENGINE_VERSION,
            "strategy": strategy_snapshot,
            "data_snapshot_hash": data_snapshot_hash,
            "run_params": run_params,
        }
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
