from __future__ import annotations

from rest_framework import serializers

from apps.core.data import available_symbols
from apps.strategies.models import Strategy
from apps.strategies.validation import (
    validate_position_sizing,
    validate_rules,
    validate_universe,
)


class StrategySerializer(serializers.ModelSerializer):
    class Meta:
        model = Strategy
        fields = [
            "id",
            "name",
            "universe",
            "rules",
            "position_sizing",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "version", "created_at", "updated_at"]
        extra_kwargs = {
            "universe": {"required": True},
            "rules": {"required": True},
        }

    def validate_rules(self, value):
        return validate_rules(value)

    def validate_position_sizing(self, value):
        return validate_position_sizing(value)

    def validate_universe(self, value):
        return validate_universe(value, available_symbols())

    def create(self, validated_data):
        validated_data["owner"] = self.context["request"].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # PATCH/PUT bumps the version (an edit produces a new logical strategy version).
        validated_data["version"] = instance.version + 1
        return super().update(instance, validated_data)
