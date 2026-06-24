from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.backtests.models import Backtest, Trade
from apps.strategies.models import Strategy


class BacktestCreateSerializer(serializers.Serializer):
    """Validates a run request. The strategy field is scoped to the requesting owner, so a backtest
    can only be run against one's own strategy."""

    strategy = serializers.PrimaryKeyRelatedField(queryset=Strategy.objects.none())
    symbol = serializers.CharField(required=False)
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    initial_capital = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        required=False,
        default=Decimal("100000.00"),
        min_value=Decimal("0.01"),
    )
    fees_bps = serializers.FloatField(required=False, default=5.0, min_value=0)
    slippage_bps = serializers.FloatField(required=False, default=5.0, min_value=0)
    oos_split_date = serializers.DateField(required=False, allow_null=True)
    periods_per_year = serializers.IntegerField(required=False, default=252, min_value=1)

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            fields["strategy"].queryset = Strategy.objects.filter(owner=request.user)
        return fields

    def validate(self, attrs):
        strategy = attrs["strategy"]
        universe = strategy.universe or []
        symbol = attrs.get("symbol") or (universe[0] if universe else None)
        if symbol is None:
            raise serializers.ValidationError({"symbol": "strategy has an empty universe"})
        if symbol not in universe:
            raise serializers.ValidationError(
                {"symbol": f"{symbol!r} is not in the strategy universe {universe}"}
            )
        attrs["symbol"] = symbol

        start, end = attrs.get("start_date"), attrs.get("end_date")
        if start and end and start > end:
            raise serializers.ValidationError({"end_date": "end_date must be on/after start_date"})
        oos = attrs.get("oos_split_date")
        if oos and start and oos < start:
            raise serializers.ValidationError(
                {"oos_split_date": "oos_split_date must be within the backtest range"}
            )
        if oos and end and oos > end:
            raise serializers.ValidationError(
                {"oos_split_date": "oos_split_date must be within the backtest range"}
            )
        return attrs


class TradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trade
        fields = [
            "symbol",
            "side",
            "qty",
            "entry_ts",
            "entry_px",
            "exit_ts",
            "exit_px",
            "fees",
            "pnl",
        ]


class BacktestSerializer(serializers.ModelSerializer):
    metrics = serializers.SerializerMethodField()
    trades = TradeSerializer(many=True, read_only=True)
    strategy_version = serializers.SerializerMethodField()

    class Meta:
        model = Backtest
        fields = [
            "id",
            "strategy",
            "strategy_version",
            "symbol",
            "status",
            "result_hash",
            "start_date",
            "end_date",
            "initial_capital",
            "fees_bps",
            "slippage_bps",
            "oos_split_date",
            "periods_per_year",
            "error",
            "created_at",
            "finished_at",
            "metrics",
            "trades",
        ]

    def get_metrics(self, obj) -> dict | None:
        result = getattr(obj, "result", None)
        return result.metrics if result else None

    def get_strategy_version(self, obj) -> int | None:
        return (obj.strategy_snapshot or {}).get("version")
