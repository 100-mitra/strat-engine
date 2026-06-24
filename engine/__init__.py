"""StratEngine backtesting engine.

A self-contained, Django-free package: importable and unit-testable on its own. The web layer
(``apps/``) depends on this package, never the reverse.

``ENGINE_VERSION`` is hand-bumped whenever a change can alter backtest output (execution model,
cost math, indicator wrapping). It is folded into ``result_hash`` so a math change invalidates
stale cached results rather than silently serving them.
"""

ENGINE_VERSION = "1.0.0"
