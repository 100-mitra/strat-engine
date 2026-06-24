from rest_framework.routers import SimpleRouter

from apps.backtests.views import BacktestViewSet

app_name = "backtests"

router = SimpleRouter()
router.register("backtests", BacktestViewSet, basename="backtest")

urlpatterns = router.urls
