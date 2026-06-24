"""Strategy domain model.

A Strategy is mutable: editing it bumps ``version``. Because backtests must stay reproducible, a
Backtest freezes a ``snapshot()`` of the strategy at run time (see apps.backtests.models) rather
than referencing the live, mutable rows here.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


def default_position_sizing() -> dict:
    return {"type": "fixed_fraction", "fraction": 1.0}


def default_rules() -> dict:
    return {
        "entry": {"logic": "AND", "conditions": []},
        "exit": {"logic": "AND", "conditions": []},
    }


class Strategy(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="strategies"
    )
    name = models.CharField(max_length=200)
    universe = models.JSONField(default=list)  # list of symbols, e.g. ["SPY"]
    rules = models.JSONField(default=default_rules)  # see engine.rules grammar
    position_sizing = models.JSONField(default=default_position_sizing)
    version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "strategies"

    def __str__(self) -> str:
        return f"{self.name} (v{self.version})"

    def snapshot(self) -> dict:
        """Frozen, hashable definition captured by each Backtest for reproducibility."""
        return {
            "name": self.name,
            "rules": self.rules,
            "universe": self.universe,
            "position_sizing": self.position_sizing,
            "version": self.version,
        }
