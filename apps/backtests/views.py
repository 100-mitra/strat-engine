"""Backtest API: synchronous run with content-addressed caching, plus result endpoints.

POST /api/backtests/ runs the engine synchronously (Phase 1). It first resolves the run's
``result_hash``; if this owner already has an identical finished backtest, a new Backtest row is
created (audit trail) that **reuses the cached computation** (copied into its own 1:1 result)
instead of recomputing. Responses carry a ``cached`` flag.
"""

from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.backtests.models import Backtest, BacktestResult, Trade
from apps.backtests.serializers import BacktestCreateSerializer, BacktestSerializer
from apps.core.data import get_data_source
from engine.backtester import BacktestError
from engine.datasource import DataSourceError
from engine.indicators import IndicatorError
from engine.metrics import generate_tearsheet_html
from engine.rules import RuleError
from engine.service import BacktestSpecError, compute_run_hash, execute_backtest

ENGINE_ERRORS = (
    DataSourceError,
    IndicatorError,
    RuleError,
    BacktestError,
    BacktestSpecError,
)


def _aware(value):
    """Normalize an engine timestamp (pandas Timestamp / datetime / None) to tz-aware UTC."""
    if value is None:
        return None
    if not isinstance(value, dt.datetime):
        value = value.to_pydatetime()
    if timezone.is_naive(value):
        value = timezone.make_aware(value, dt.UTC)
    return value


class BacktestViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Backtest.objects.filter(owner=self.request.user)
            .select_related("strategy", "result")
            .prefetch_related("trades")
        )

    def get_serializer_class(self):
        return BacktestCreateSerializer if self.action == "create" else BacktestSerializer

    def create(self, request, *args, **kwargs):
        serializer = BacktestCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        strategy = data["strategy"]
        snapshot = strategy.snapshot()
        run_params = {
            "symbol": data["symbol"],
            "start": data["start_date"].isoformat() if data.get("start_date") else None,
            "end": data["end_date"].isoformat() if data.get("end_date") else None,
            "initial_capital": float(data["initial_capital"]),
            "fees_bps": float(data["fees_bps"]),
            "slippage_bps": float(data["slippage_bps"]),
            "oos_split_date": (
                data["oos_split_date"].isoformat() if data.get("oos_split_date") else None
            ),
            "periods_per_year": int(data["periods_per_year"]),
        }

        data_source = get_data_source()
        try:
            result_hash = compute_run_hash(data_source, snapshot, run_params)
            cached = (
                Backtest.objects.filter(
                    owner=request.user, result_hash=result_hash, status=Backtest.Status.DONE
                )
                .select_related("result")
                .filter(result__isnull=False)
                .prefetch_related("trades")
                .first()
            )

            backtest = self._new_backtest(request.user, strategy, snapshot, data, result_hash)
            if cached is not None:
                self._copy_cached(cached, backtest)
                is_cached = True
            else:
                output = execute_backtest(data_source, snapshot, run_params)
                self._persist_output(backtest, output)
                is_cached = False
        except ENGINE_ERRORS as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        body = BacktestSerializer(backtest, context={"request": request}).data
        body["cached"] = is_cached
        if is_cached:
            body["source_backtest_id"] = cached.id
        return Response(body, status=status.HTTP_201_CREATED)

    # --- helpers -----------------------------------------------------------
    def _new_backtest(self, user, strategy, snapshot, data, result_hash) -> Backtest:
        return Backtest(
            owner=user,
            strategy=strategy,
            strategy_snapshot=snapshot,
            symbol=data["symbol"],
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            initial_capital=data["initial_capital"],
            fees_bps=data["fees_bps"],
            slippage_bps=data["slippage_bps"],
            oos_split_date=data.get("oos_split_date"),
            periods_per_year=data["periods_per_year"],
            status=Backtest.Status.DONE,
            result_hash=result_hash,
            finished_at=timezone.now(),
        )

    @transaction.atomic
    def _persist_output(self, backtest: Backtest, output) -> None:
        backtest.save()
        BacktestResult.objects.create(
            backtest=backtest,
            metrics=output.metrics,
            equity_curve=output.equity_curve,
            data_snapshot_hash=output.data_snapshot_hash,
        )
        self._create_trades(backtest, output.trades)

    @transaction.atomic
    def _copy_cached(self, cached: Backtest, backtest: Backtest) -> None:
        backtest.save()
        src = cached.result
        BacktestResult.objects.create(
            backtest=backtest,
            metrics=src.metrics,
            equity_curve=src.equity_curve,
            data_snapshot_hash=src.data_snapshot_hash,
        )
        Trade.objects.bulk_create(
            Trade(
                backtest=backtest,
                symbol=t.symbol,
                side=t.side,
                qty=t.qty,
                entry_ts=t.entry_ts,
                entry_px=t.entry_px,
                exit_ts=t.exit_ts,
                exit_px=t.exit_px,
                fees=t.fees,
                pnl=t.pnl,
            )
            for t in cached.trades.all()
        )

    def _create_trades(self, backtest: Backtest, trades: list[dict]) -> None:
        Trade.objects.bulk_create(
            Trade(
                backtest=backtest,
                symbol=t["symbol"],
                side=t["side"],
                qty=t["qty"],
                entry_ts=_aware(t["entry_ts"]),
                entry_px=t["entry_px"],
                exit_ts=_aware(t["exit_ts"]),
                exit_px=t["exit_px"],
                fees=t["fees"],
                pnl=t["pnl"],
            )
            for t in trades
        )

    # --- result endpoints --------------------------------------------------
    @action(detail=True, methods=["get"], url_path="equity-curve")
    def equity_curve(self, request, pk=None):
        backtest = self.get_object()
        result = getattr(backtest, "result", None)
        if result is None:
            return Response({"detail": "no result for this backtest"}, status=404)
        return Response(
            {
                "initial_capital": float(backtest.initial_capital),
                "oos_boundary_date": (
                    backtest.oos_split_date.isoformat() if backtest.oos_split_date else None
                ),
                "points": result.equity_curve,
            }
        )

    @action(detail=True, methods=["get"], url_path="tearsheet")
    def tearsheet(self, request, pk=None):
        import pandas as pd

        backtest = self.get_object()
        result = getattr(backtest, "result", None)
        if result is None:
            return Response({"detail": "no result for this backtest"}, status=404)
        points = result.equity_curve or []
        equity = pd.Series(
            [p["equity"] for p in points],
            index=pd.to_datetime([p["date"] for p in points]),
        )
        returns = equity.pct_change().dropna()  # drop the undefined first-bar return
        html = generate_tearsheet_html(
            returns,
            title=f"StratEngine — {backtest.symbol}",
            periods_per_year=backtest.periods_per_year,
        )
        return HttpResponse(html, content_type="text/html")
