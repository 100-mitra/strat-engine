from django.http import HttpResponse
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core import __version__

_LANDING_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>StratEngine</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 16px/1.6 system-ui, sans-serif; max-width: 760px; margin: 3rem auto; padding: 0 1.2rem; }}
  h1 {{ margin-bottom: .2rem; }} .tag {{ color: #888; margin-top: 0; }}
  code, pre {{ background: rgba(127,127,127,.15); border-radius: 6px; }}
  code {{ padding: .1rem .35rem; }} pre {{ padding: 1rem; overflow-x: auto; }}
  a {{ color: #3b82f6; }} ul {{ padding-left: 1.2rem; }} li {{ margin: .25rem 0; }}
  .ok {{ color: #16a34a; font-weight: 600; }}
</style></head><body>
<h1>StratEngine <span class="ok">&#9679; live</span></h1>
<p class="tag">Rule-based strategy backtesting backend &middot; Django REST + PostgreSQL + a
look-ahead-safe engine &middot; v{version}</p>

<p>This is a JSON REST API (there is no web UI). Endpoints:</p>
<ul>
  <li><a href="/healthz/">/healthz/</a> &mdash; liveness</li>
  <li><code>POST /api/auth/token/</code> &mdash; obtain a token</li>
  <li><code>/api/strategies/</code> &middot; <code>/api/backtests/</code> &middot;
      <code>/api/backtests/&lt;id&gt;/equity-curve/</code> &middot;
      <code>/api/backtests/&lt;id&gt;/tearsheet/</code></li>
  <li><a href="/api/strategies/">browsable API</a> (login required) &middot;
      <a href="/admin/">/admin/</a></li>
</ul>

<p><strong>Demo login:</strong> <code>demo</code> / <code>demo-pass-12345</code>
(seeded strategy is id <code>1</code>). Try it:</p>
<pre>BASE={base}
TOKEN=$(curl -s -X POST $BASE/api/auth/token/ -H "Content-Type: application/json" \\
  -d '{{"username":"demo","password":"demo-pass-12345"}}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -X POST $BASE/api/backtests/ -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \\
  -d '{{"strategy": 1, "oos_split_date": "2022-01-01"}}'</pre>

<p>Source &amp; docs: <a href="https://github.com/100-mitra/strat-engine">github.com/100-mitra/strat-engine</a></p>
</body></html>"""


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def index(request: Request) -> HttpResponse:
    """Friendly landing page at the root, so the live URL isn't a bare 404."""
    base = request.build_absolute_uri("/").rstrip("/")
    return HttpResponse(_LANDING_HTML.format(version=__version__, base=base))


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def healthz(_request: Request) -> Response:
    """Liveness probe. Intentionally does not touch the database so it stays green
    during transient DB blips (liveness != readiness)."""
    return Response({"status": "ok", "service": "stratengine", "version": __version__})
