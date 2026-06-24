from __future__ import annotations

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.strategies.models import Strategy
from apps.strategies.serializers import StrategySerializer


class StrategyViewSet(viewsets.ModelViewSet):
    """Owner-scoped CRUD for strategies.

    The queryset is filtered to ``request.user`` so another owner's objects are invisible — access
    attempts return 404 (we don't leak existence). PATCH/PUT bump the strategy version.
    """

    serializer_class = StrategySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Strategy.objects.filter(owner=self.request.user)
