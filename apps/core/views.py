from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core import __version__


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def healthz(_request: Request) -> Response:
    """Liveness probe. Intentionally does not touch the database so it stays green
    during transient DB blips (liveness != readiness)."""
    return Response({"status": "ok", "service": "stratengine", "version": __version__})
