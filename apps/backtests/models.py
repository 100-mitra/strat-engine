"""Backtest, BacktestResult, and Trade models.

Reproducibility & caching:
- ``Backtest.strategy_snapshot`` freezes the strategy definition at run time, so editing the
  strategy later never changes a past backtest.
- ``Backtest.result_hash`` content-addresses the run. Re-submitting an identical backtest creates a
  new Backtest row (audit trail) but **reuses** the cached computation by copying it into this row's
  own 1:1 ``BacktestResult`` instead of recomputing (see apps.backtests.views).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Backtest(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        DONE = "done"
        FAILED = "failed"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="backtests"
    )
    strategy = models.ForeignKey(
        "strategies.Strategy", on_delete=models.CASCADE, related_name="backtests"
    )
    strategy_snapshot = models.JSONField()  # frozen strategy definition at run time

    symbol = models.CharField(max_length=50)  # single-symbol MVP (drawn from the strategy universe)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    initial_capital = models.DecimalField(max_digits=20, decimal_places=2, default=100000)
    fees_bps = models.FloatField(default=5.0)
    slippage_bps = models.FloatField(default=5.0)
    oos_split_date = models.DateField(null=True, blank=True)
    periods_per_year = models.IntegerField(default=252)

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True
    )
    result_hash = models.CharField(max_length=64, blank=True, db_index=True)
    error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Backtest #{self.pk} ({self.symbol}, {self.status})"


class BacktestResult(models.Model):
    backtest = models.OneToOneField(Backtest, on_delete=models.CASCADE, related_name="result")
    metrics = models.JSONField(default=dict)
    equity_curve = models.JSONField(default=list)  # [{date, equity, region}]
    # Tearsheets are generated on demand (stateless, ephemeral-fs-safe); this stays optional.
    tearsheet_path = models.CharField(max_length=500, blank=True)
    data_snapshot_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Result for Backtest #{self.backtest_id}"


class Trade(models.Model):
    backtest = models.ForeignKey(Backtest, on_delete=models.CASCADE, related_name="trades")
    symbol = models.CharField(max_length=50)
    side = models.CharField(max_length=5, choices=[("long", "Long")], default="long")
    qty = models.FloatField()
    entry_ts = models.DateTimeField(null=True, blank=True)
    entry_px = models.FloatField(null=True, blank=True)
    exit_ts = models.DateTimeField(null=True, blank=True)
    exit_px = models.FloatField(null=True, blank=True)
    fees = models.FloatField(default=0.0)
    pnl = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["entry_ts", "id"]

    def __str__(self) -> str:
        return f"{self.side} {self.qty:.4f} {self.symbol}"
