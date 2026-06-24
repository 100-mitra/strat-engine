from rest_framework.routers import SimpleRouter

from apps.strategies.views import StrategyViewSet

app_name = "strategies"

router = SimpleRouter()
router.register("strategies", StrategyViewSet, basename="strategy")

urlpatterns = router.urls
