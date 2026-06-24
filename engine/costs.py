"""Transaction costs: fees and slippage.

Two independent effects, both applied on every fill:

- **Slippage** (market impact) moves the fill price *against* you relative to the bar's open:
  a buy fills higher, a sell fills lower.
- **Fee** (commission) is charged on the traded notional (price * qty) of each fill.

Both default to a nonzero 5 bps (1 bps = 0.01%). The known-answer test
(``tests/test_known_answer.py``) hand-computes an equity curve against exactly this math.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_FEES_BPS = 5.0
DEFAULT_SLIPPAGE_BPS = 5.0
_BPS = 1e4


@dataclass(frozen=True)
class CostModel:
    fees_bps: float = DEFAULT_FEES_BPS
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS

    def buy_fill_price(self, open_price: float) -> float:
        """Buy fills at the next bar's open, nudged up by slippage."""
        return open_price * (1.0 + self.slippage_bps / _BPS)

    def sell_fill_price(self, open_price: float) -> float:
        """Sell fills at the next bar's open, nudged down by slippage."""
        return open_price * (1.0 - self.slippage_bps / _BPS)

    def fee(self, notional: float) -> float:
        """Commission on a fill's traded notional (price * qty)."""
        return abs(notional) * self.fees_bps / _BPS
