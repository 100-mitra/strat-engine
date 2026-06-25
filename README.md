# StratEngine

A **rule-based strategy backtesting backend** built on Django REST Framework + PostgreSQL around a
small, **framework-free, look-ahead-safe** backtesting engine. You define a strategy as a JSON
entry/exit rule grammar (indicators + price + value, combined with AND/OR), run it over historical
OHLCV data through a REST API, and get back reproducible metrics, a charting-ready equity curve, and
a QuantStats HTML tearsheet.

The point of this project is **backend systems rigor in a quant domain**: clean API design,
swappable abstractions, strict validation, reproducible/idempotent runs, and — above all —
**correctness** (no look-ahead bias, modeled costs, out-of-sample reporting). It is a
paper/historical-data-only research tool: no real orders, no money, no AI/ML.

## Live demo

**https://web-production-99f9d7.up.railway.app** (Railway; the instance may cold-start on the first
hit). It is pre-seeded, so you can run a backtest immediately:

- Demo login — username `demo`, password `demo-pass-12345`
- Seeded strategy is **id 1** (RSI(2) mean reversion + SMA(200) trend filter, ~38 trades on SPY)

```bash
BASE=https://web-production-99f9d7.up.railway.app
curl -s $BASE/healthz/
TOKEN=$(curl -s -X POST $BASE/api/auth/token/ -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo-pass-12345"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
# run the seeded backtest with an in/out-of-sample split
curl -s -X POST $BASE/api/backtests/ -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  -d '{"strategy": 1, "oos_split_date": "2022-01-01"}'
# then open  $BASE/api/backtests/1/tearsheet/  (sending the Authorization header) for the report
```

---

## Table of contents
- [Live demo](#live-demo)
- [Architecture](#architecture)
- [Correctness guarantees](#correctness-guarantees)
- [Quickstart](#quickstart)
- [Rule grammar](#rule-grammar)
- [API](#api)
- [Measured numbers](#measured-numbers)
- [Testing](#testing)
- [Deploy](#deploy)
- [Limitations](#limitations)
- [Project layout](#project-layout)

---

## Architecture

```
                    HTTP (token auth)
  client ──────────────────────────────────►  Django + DRF  (apps/)
                                               ├─ core         health, token auth, data bridge
                                               ├─ strategies   Strategy model, strict rule validation, CRUD
                                               └─ backtests    Backtest/Result/Trade, run + cache, endpoints
                                                        │
                                                        │ plain dicts / pandas (no Django types cross this line)
                                                        ▼
                                               engine/  (framework-free, unit-testable on its own)
                                               ├─ datasource   DataSource ABC ─► CSV / yfinance, data_snapshot_hash
                                               ├─ indicators   registry over `ta` (SMA/EMA/RSI/ADX/ATR)
                                               ├─ rules        operands + 6 operators + AND/OR evaluator
                                               ├─ costs        fees + slippage
                                               ├─ backtester   next-bar-open execution, equity curve, trades
                                               ├─ metrics      quantstats-lumi wrappers + HTML tearsheet
                                               ├─ reproducibility  result_hash
                                               └─ service      execute_backtest orchestration
                                                        │
                                               PostgreSQL (Strategy, Backtest, BacktestResult, Trade)
```

**Two swappable interfaces** (literal JD language): `DataSource` (CSV today, yfinance behind the
same interface, a broker feed later) and `Broker` (reserved for Phase 3 paper trading). Indicators
and rule-operators live in **registries**, so the API never hard-codes a strategy vocabulary.

The hard boundary: `engine/` imports no Django. It is importable and testable standalone, which is
why the correctness tests run as pure `pytest` against real data with no web stack involved.

---

## Correctness guarantees

These are acceptance criteria, each backed by a test.

| Guarantee | How it's enforced | Test |
|-----------|-------------------|------|
| **No look-ahead bias** | Signals at bar *t* use data ≤ *t*; a signal at *t* fills at **t+1's open**. | `tests/test_no_lookahead.py` — truncation invariant: running on `data[:T]` yields identical signals/positions/equity for all `t<T` as the full run, across random cutoffs on real data. |
| **Causal indicators** | `ta` indicators wrapped with `fillna=False`; warmup stays NaN. | `tests/test_indicators_causal.py` — proves `indicator(data[:k])[-1] == indicator(full)[k-1]` for SMA/EMA/RSI/ADX/ATR. |
| **Modeled costs** | `fees_bps` on each fill's notional + `slippage_bps` against the fill price; nonzero 5/5 defaults. | `tests/test_costs.py` |
| **Known answer** | Hand-computed equity curve on a tiny fixture, zero costs, isolating next-bar timing. | `tests/test_known_answer.py` |
| **Reproducibility / idempotency** | `result_hash = sha256(ENGINE_VERSION + strategy_snapshot + data_snapshot_hash + resolved run_params)`; identical re-runs are served from cache. | `tests/test_service.py`, `tests/test_api_backtests.py` |
| **Out-of-sample** | `oos_split_date` partitions realized returns; metrics reported per segment. | `tests/test_service.py`, `tests/test_api_backtests.py` |
| **Reproducible after edits** | Each `Backtest` freezes a `strategy_snapshot`; editing the strategy (which bumps `version`) never changes a past backtest. | enforced by model design |
| **Metric correctness** | CAGR is computed directly (bar-count years, not QuantStats' calendar-day divisor); the undefined first-bar return is dropped before risk metrics; in/out-of-sample metrics derive from each segment's own equity sub-series (no boundary leak). | `tests/test_metrics_regression.py` |

Execution model in one line: **buy fill = `open·(1 + slippage)`, sell fill = `open·(1 − slippage)`,
fee = `bps · notional` on each side, fractional shares, long-only, end-of-data mark-to-market.**

---

## Quickstart

### Docker (recommended)

```bash
docker compose up --build           # web (Django) + db (Postgres)
curl http://localhost:8000/healthz/ # {"status":"ok","service":"stratengine","version":"0.1.0"}

# seed a demo user + token + demo strategy, and print a ready-to-run curl
docker compose exec web python manage.py seed_demo
```

### Local (Python 3.12)

```bash
py -3.12 -m venv .venv
./.venv/Scripts/python -m pip install -e ".[dev]"   # Windows (POSIX: .venv/bin/python)
pytest                                              # 68 tests
ruff check . && black --check .
python manage.py migrate && python manage.py seed_demo
python manage.py runserver
```

Without `DATABASE_URL`, settings fall back to a local SQLite file so a fresh clone can run the suite
with no Postgres. Docker and CI set Postgres.

---

## Rule grammar

A strategy's `rules` has an `entry` and an `exit` group; each group is a flat list of `conditions`
combined by a single `logic` (`AND`/`OR`). A condition is `{left, operator, right}`.

- **Operands**: `{"type":"indicator","name":"SMA","params":{"window":20},"on":"close"}`,
  `{"type":"price","field":"close"}`, or `{"type":"value","value":70}`.
- **Operators**: `>`, `<`, `>=`, `<=`, `crosses_above`, `crosses_below`.
- **Indicators**: `SMA`, `EMA`, `RSI`, `ADX`, `ATR` (unknown → `400`).

Example — RSI(2) mean reversion with a trend filter (the seeded demo, ~38 trades on SPY):

```json
{
  "entry": {"logic": "AND", "conditions": [
    {"left": {"type": "indicator", "name": "RSI", "params": {"window": 2}}, "operator": "<", "right": {"type": "value", "value": 15}},
    {"left": {"type": "price", "field": "close"}, "operator": ">", "right": {"type": "indicator", "name": "SMA", "params": {"window": 200}}}
  ]},
  "exit": {"logic": "OR", "conditions": [
    {"left": {"type": "indicator", "name": "RSI", "params": {"window": 2}}, "operator": ">", "right": {"type": "value", "value": 70}}
  ]}
}
```

Validation is strict: empty rule lists, unknown indicators/operators, bad price fields, non-positive
windows, `value`-vs-`value` conditions, unexpected fields, and unknown universe symbols all return a
descriptive `400`.

---

## API

```
POST   /api/auth/token/                      obtain a token (username/password)
POST   /api/strategies/                      create (validates the rule grammar)
GET    /api/strategies/                      list (owner-scoped, paginated)
GET    /api/strategies/{id}/                 retrieve
PATCH  /api/strategies/{id}/                 update (bumps version)
DELETE /api/strategies/{id}/                 delete
POST   /api/backtests/                       run synchronously -> 201 {id, status, metrics, cached}
GET    /api/backtests/{id}/                  status + metrics + trades
GET    /api/backtests/{id}/equity-curve/     JSON series for charting (region-tagged)
GET    /api/backtests/{id}/tearsheet/        QuantStats HTML report (text/html)
GET    /healthz/                             liveness (no auth)
```

Everything except `/healthz/` and token issuance is owner-scoped behind token auth; cross-owner
access returns `404` (existence is not leaked).

### Example session

```bash
# 1) token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo-pass-12345"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")

# 2) create a strategy
SID=$(curl -s -X POST http://localhost:8000/api/strategies/ \
  -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"SMA50 cross","universe":["SPY"],
       "rules":{"entry":{"logic":"AND","conditions":[{"left":{"type":"price","field":"close"},"operator":"crosses_above","right":{"type":"indicator","name":"SMA","params":{"window":50}}}]},
                "exit":{"logic":"AND","conditions":[{"left":{"type":"price","field":"close"},"operator":"crosses_below","right":{"type":"indicator","name":"SMA","params":{"window":50}}}]}}}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['id'])")

# 3) run a backtest (in-sample / out-of-sample split at 2022-01-01)
curl -s -X POST http://localhost:8000/api/backtests/ \
  -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  -d "{\"strategy\": $SID, \"oos_split_date\": \"2022-01-01\"}"

# 4) charting series + tearsheet
curl -s http://localhost:8000/api/backtests/1/equity-curve/ -H "Authorization: Token $TOKEN"
curl -s http://localhost:8000/api/backtests/1/tearsheet/   -H "Authorization: Token $TOKEN" -o tearsheet.html
```

A duplicate `POST /api/backtests/` with identical inputs returns a new backtest record (audit trail)
with `"cached": true` and `"source_backtest_id"`, reusing the cached computation rather than
recomputing.

---

## Measured numbers

Measured on the committed SPY fixture (1258 daily bars, RSI + SMA(200) strategy), Python 3.12:

| Metric | Value |
|--------|-------|
| Engine backtest latency | **~15 ms** mean / ~14 ms p50 per run (1258 bars) |
| Engine throughput | **~65 backtests/sec/core** (synchronous) |
| API `POST /api/backtests/` | ~40–60 ms warm (uncached); ~40 ms cached; first request ~1.4 s (cold worker imports) |
| Tests | **73 passing** |
| Coverage | **88%** overall; engine core 93–100% |

(Reproduce latency with the snippet in the engine docstrings or the `engine.service.execute_backtest`
path; coverage via `pytest --cov`.)

---

## Testing

```bash
pytest                                   # all 73 tests
pytest --cov --cov-report=term-missing   # with coverage
```

The headline tests live in `tests/`:
`test_no_lookahead.py` (truncation invariant), `test_indicators_causal.py`,
`test_known_answer.py`, `test_costs.py`, `test_service.py` (hash/determinism/OOS/tearsheet),
and the API suites `test_api_strategies.py` / `test_api_backtests.py`.

CI (GitHub Actions, `.github/workflows/ci.yml`) runs `ruff` + `black --check` + `pytest` against a
real **PostgreSQL 15** service, installing the fully-pinned `requirements.lock`.

---

## Deploy

Deploy config is provided for **both** platforms; pick one. Both build the `Dockerfile` and provision
Postgres. Each runs migrations and `seed_demo` automatically so the live demo is immediately runnable.

> 2026 free-tier reality: a persistent public demo realistically costs ~$5–7/mo. Render's free web
> service cold-starts after ~15 min idle and its free Postgres expires after ~30 days; Railway is
> trial-credit/paid but has no cold starts. Tearsheets are generated **on demand**, so neither
> platform's ephemeral filesystem matters.

### Render (`render.yaml`)
1. Push this repo to GitHub.
2. render.com → **New → Blueprint** → select the repo. Render reads `render.yaml` (web service +
   Postgres, `SECRET_KEY` auto-generated, `DEBUG=0`).
3. After the first deploy, the live URL is `https://<service>.onrender.com`. Health: `/healthz/`.
4. Get the demo token: Render **Shell** → `python manage.py seed_demo` (also run automatically
   pre-deploy).

### Railway (`railway.json`)  — this is what the live demo runs on
1. Push to GitHub (or deploy the local dir with `railway up`).
2. railway.com → **New Project** → add a **PostgreSQL** service, and a service for this repo
   (Dockerfile build). On the web service set variables: `DATABASE_URL=${{Postgres.DATABASE_URL}}`,
   a random `SECRET_KEY`, `DEBUG=0`, `ALLOWED_HOSTS=*`, and **`PORT=8000`** (Railway routes to this
   port; it does not inject `PORT` itself).
3. The image's entrypoint runs `migrate` + `seed_demo`, then gunicorn on `$PORT` — so there is **no**
   custom start command (a start command would bypass the entrypoint). Generate a domain with
   **target port 8000**. Live URL: `https://<service>.up.railway.app`.

### AWS (stretch note)
The same container runs on ECS Fargate (or App Runner) behind an ALB with RDS PostgreSQL and
secrets in SSM Parameter Store / Secrets Manager — `DATABASE_URL`, `SECRET_KEY`, and `ALLOWED_HOSTS`
are the only required env vars, so no code changes are needed.

---

## Limitations

Honest scope boundaries (correctness over breadth):

- **Survivorship bias.** The MVP uses a fixed, currently-liquid universe (SPY, BTC-USD). Delisted
  instruments are not modeled, so a broader-universe backtest would be optimistic.
- **Out-of-sample is a metrics partition, not walk-forward.** Signals are computed once over the
  full range; `oos_split_date` only splits the realized returns for separate reporting. True
  walk-forward re-optimization is Phase 2.
- **Unadjusted prices.** OHLC is not dividend/split-adjusted; SPY total return is understated by its
  dividend yield (see `data/README.md`).
- **Single-symbol backtests.** One symbol per backtest in Phase 1; the data model already stores a
  `universe` list for a multi-symbol extension.
- **Single timeframe.** Daily bars only — no intraday or multi-timeframe support. ("Next bar" is the
  next daily row.)
- **Long-only.** Short-selling is a Phase 2 toggle.
- **Best-effort concurrency.** The Phase 1 run path is synchronous; two truly-simultaneous identical
  submissions could both compute (worst case: redundant work). Async jobs + locking are Phase 2.
- **Library note.** Metrics use `quantstats-lumi`, the maintained QuantStats fork (the original is
  unmaintained and breaks on modern numpy/pandas).

---

## Project layout

```
config/      Django settings, urls, wsgi/asgi
apps/
  core/      health, token auth, settings→engine data bridge, seed_demo command
  strategies/ Strategy model, strict rule validation, CRUD
  backtests/  Backtest/Result/Trade models, run+cache views, endpoints
engine/      framework-free backtesting engine (see Architecture)
brokers/     reserved for Phase 3 paper trading
data/        committed OHLCV CSV fixtures (+ provenance/limitations)
tests/       engine correctness + API integration tests
```

See [the project brief](StratEngine_Project-Brief_for-Claude-Code.md) for the full phased spec.
Phase 1 (this) is a complete, shippable artifact; Phases 2–3 (async jobs, more indicators, paper
trading) are documented but intentionally out of scope here.
