"""Root URL configuration for StratEngine."""

from django.contrib import admin
from django.urls import include, path

from apps.core.views import healthz

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", healthz, name="healthz"),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.strategies.urls")),
    path("api/", include("apps.backtests.urls")),
]
