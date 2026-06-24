# StratEngine

A rule-based strategy **backtesting** backend (with a paper-trading roadmap), built on Django REST
Framework + PostgreSQL around a small, framework-free, look-ahead-safe backtesting engine.

> Status: **Phase 0 (skeleton)** in progress. See
> [the project brief](StratEngine_Project-Brief_for-Claude-Code.md) for the full spec and phases.

## Quickstart (Docker)

```bash
docker compose up --build      # boots web (Django) + db (Postgres)
curl http://localhost:8000/healthz/   # -> {"status": "ok", ...}
```

## Local development (Python 3.12)

```bash
py -3.12 -m venv .venv
./.venv/Scripts/python -m pip install -e ".[dev]"   # Windows
pytest
ruff check . && black --check .
```

More documentation (architecture, correctness guarantees, API examples, deploy steps, and
limitations) lands with Phase 1.
