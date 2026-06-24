# StratEngine — Project Brief for Claude Code
**A rule-based strategy backtesting (and paper-trading) backend.**
Working name: *StratEngine* (rename freely). Target application: Invsto — Backend Engineer Intern. Prepared 2026-06-23.

---

## 0. How to use this doc (read first, Claude Code)

This is a build spec, not a suggestion. Follow the **phases in order**. Build **Phase 0 + Phase 1 only**, get them deployed and green, then **stop and ask the human** before starting Phase 2. Phase 1 is a complete, shippable artifact on its own.

Hard rules for this project:
- **A small, correct, deployed thing beats a big broken one.** Do not start a later phase until the current one is tested, committed, and deployed.
- **Quant-correctness is non-negotiable** (Section 4). A subtly wrong backtest is worse than no project — a quant will inspect this.
- **This is plain backend engineering.** No LLMs, no AI agents, no ML. The star is the *system* (API design, abstractions, persistence, reproducibility), not the trading math.
- **Paper/sandbox/historical data only. Never real money, never real orders.** Non-custodial by design.
- Keep it **broker-agnostic and data-source-agnostic** so it can be reused for other fintech applications, not just this one.

---

## 1. Why this exists (context)

Invsto is a low-to-mid-frequency trading-tools startup. Their flagship (Sharksigma) does strategy research + backtesting, and their open-source `0xTradingSim` (github.com/sharksigma/tradingsim) uses a **rule-based entry/exit grammar** with the Python `ta` and `QuantStats` libraries. The JD wants **Python, Django, PostgreSQL, REST APIs, OOP, AWS** and "efficient and reusable backend abstractions and systems."

This project rebuilds that strategy-research surface as a **production-grade Django backend**, on the exact stack the JD screens for. The point is to demonstrate backend systems skill in their domain — *not* to clone their repo line-for-line.

> Honest caveats to keep in mind: Invsto's only public backend is TypeScript, not Django — we target the JD's stated stack deliberately. `0xTradingSim` is a small/old reference; treat its rule grammar as *inspiration*, and build idiomatic Django. This is a portfolio/learning artifact, not investment advice.

---

## 2. Design principles (the critical thinking, baked in)

1. **Backend-first framing.** The engine is one module; the impressive part is the service around it — clean REST API, validation, async jobs, idempotency, audit, tests, deploy. Build accordingly.
2. **Correctness as the headline feature.** No look-ahead bias, modeled costs, out-of-sample validation, reproducible runs. These are what separate this from the thousands of toy backtesters.
3. **Reusable abstractions** (this is literal JD language). Two interfaces must be swappable: `DataSource` (CSV, yfinance, broker API…) and `Broker` (paper, Alpaca sandbox…). Indicators and rule-operators live in registries, not hard-coded branches.
4. **Reproducibility / idempotency.** Every backtest is deterministic; identical inputs return a cached result by hash. (Carry this signature strength over from prior work.)
5. **Scope discipline.** Phase 1 is the deliverable. Everything else is upside.

---

## 3. Tech stack

- **Language:** Python 3.11+
- **Web:** Django 5.x + Django REST Framework
- **DB:** PostgreSQL 15+ (use the Django ORM)
- **Engine:** pandas, numpy, [`ta`](https://github.com/bukosabino/ta) for indicators, [`QuantStats`](https://github.com/ranaroussi/quantstats) for metrics/tearsheets
- **Async (Phase 2):** Celery + Redis
- **Auth:** DRF Token authentication
- **Infra:** Docker + docker-compose (web, db, redis); GitHub Actions CI (ruff/black + pytest)
- **Deploy:** Render or Railway free tier (document the steps); AWS notes in README as a stretch (closes the JD's AWS keyword)
- **Data:** ship small committed OHLCV CSV fixtures (e.g., BTC-USD and SPY daily); optional `yfinance` loader behind the `DataSource` interface

---

## 4. Quant-correctness requirements (MANDATORY — do not skip)

These are acceptance criteria, not nice-to-haves.

- **No look-ahead bias.** Signals computed from bar *t*'s OHLC are actionable only at **bar t+1's open** (next-bar execution). Indicators at bar *t* may use data only up to and including *t*.
  - **Invariant test (the headline test):** for random cutoff index `T`, running the engine on `data[:T]` must produce **identical** signal/position series for all `t < T` as running on the full dataset. Assert equality. If future data can change past signals, the test fails.
- **Transaction costs + slippage.** Apply `fees_bps` per trade and `slippage_bps` to fill prices. Defaults must be **nonzero** (e.g., 5 bps fee, 5 bps slippage).
- **Out-of-sample split.** Support an in-sample / out-of-sample date boundary and report metrics **separately** for each. (Stretch: rolling walk-forward.)
- **Survivorship bias.** MVP uses a fixed liquid universe; **document this limitation explicitly** in the README. (Stretch: delisting-inclusive data.)
- **Reproducibility.** `result_hash = sha256(strategy_definition + data_snapshot_hash + run_params)`. Re-submitting an identical backtest returns the cached result instead of recomputing. Add a test proving same-inputs → same hash.
- **Known-answer test.** A trivial strategy on a tiny hand-built fixture with a hand-computed expected equity curve; assert the engine matches.

---

## 5. Domain model (PostgreSQL via Django ORM)

- **User** — Django auth user.
- **Strategy** — `owner` (FK), `name`, `universe` (list of symbols), `rules` (JSON, see §6), `position_sizing` (e.g., fixed fraction), `version` (int, bump on edit), `created_at`.
- **Backtest** — `strategy` (FK), `start_date`, `end_date`, `initial_capital`, `fees_bps`, `slippage_bps`, `oos_split_date` (nullable), `status` (`queued|running|done|failed`), `result_hash`, `created_at`, `finished_at`.
- **BacktestResult** — `backtest` (FK 1:1), `metrics` (JSON: CAGR, Sharpe, Sortino, max_drawdown, win_rate, num_trades, in/out-of-sample variants), `equity_curve` (JSON or file ref), `tearsheet_path`.
- **Trade** — `backtest` (FK), `symbol`, `side`, `qty`, `entry_ts`, `entry_px`, `exit_ts`, `exit_px`, `pnl`. (Also reused by Phase 3 paper trading.)

---

## 6. Rule grammar (echoes 0xTradingSim; validate strictly)

A strategy has `entry_rules` and `exit_rules`, each a list of conditions combined with `AND`/`OR`. A condition is `{ left, operator, right }`:

- **Operand** is one of:
  - `{"type": "indicator", "name": "SMA", "params": {"window": 20}, "on": "close"}`
  - `{"type": "price", "field": "close"}`  (open/high/low/close/volume)
  - `{"type": "value", "value": 70}`
- **Operator** ∈ `>`, `<`, `>=`, `<=`, `crosses_above`, `crosses_below`.
- Example (RSI oversold + trend filter): entry = `RSI(14) < 30` AND `close > SMA(200)`; exit = `RSI(14) > 55`.

Implementation notes:
- **Indicator registry**: `name -> callable` wrapping `ta` (start with SMA, EMA, RSI, ADX, ATR). Reject unknown indicators with a clear `400`.
- **Operator registry**: same pattern; `crosses_above/below` need the previous bar.
- **Long-only** for MVP (mirrors their sim). Short-selling is a Phase 2 toggle.
- Strict serializer validation: unknown fields, bad windows, or malformed conditions return descriptive `400`s. (Good validation = visible backend rigor.)

---

## 7. REST API (DRF)

```
POST   /api/auth/token/                 # obtain token
POST   /api/strategies/                 # create (validates rule grammar)
GET    /api/strategies/                 # list (owner-scoped, paginated)
GET    /api/strategies/{id}/
PATCH  /api/strategies/{id}/            # bumps version
POST   /api/backtests/                  # run backtest -> {id, status}
GET    /api/backtests/{id}/             # status + metrics
GET    /api/backtests/{id}/equity-curve/   # JSON series for charting
GET    /api/backtests/{id}/tearsheet/      # QuantStats HTML report
GET    /healthz/                        # liveness
```

- Everything owner-scoped behind token auth (except `/healthz/` and token issue).
- Phase 1: `POST /api/backtests/` runs **synchronously** and returns the finished result (keep MVP simple).
- Phase 2: it returns `202 {id, status:"queued"}` and the client polls `GET /api/backtests/{id}/`.

---

## 8. Phases & acceptance criteria

### Phase 0 — Skeleton (½ day)
Django + DRF + Postgres, docker-compose (web+db), GitHub Actions running ruff + pytest, `/healthz/`, README stub.
**Done when:** `docker-compose up` boots; CI is green; health endpoint returns 200.

### Phase 1 — MVP backtest service ← **THIS IS THE DELIVERABLE; STOP HERE**
Strategy CRUD + rule grammar (SMA/EMA/RSI/ADX, price, value; all 6 operators); synchronous **look-ahead-safe** vectorized engine with fees + slippage; QuantStats tearsheet + equity-curve endpoint; token auth; one seeded demo strategy on a committed CSV; deployed with a public live-demo URL.
**Tests required:** look-ahead invariant test, idempotency/hash test, known-answer test, indicator unit tests, API integration tests. Document coverage.
**README required:** what/why, architecture diagram, the correctness guarantees (§4), measured numbers (backtest latency, throughput, test count/coverage), API examples (curl), deploy steps, and an honest "limitations" section.
**Done when:** a stranger can clone, `docker-compose up`, hit the live demo, run the seeded backtest, and see a tearsheet — and all tests pass in CI.

### Phase 2 — Production hardening (only after Phase 1 ships)
Celery + Redis async jobs with polling; in-sample/out-of-sample reporting; short-selling toggle; rate limiting; structured logging; OpenAPI/Swagger docs; more indicators.

### Phase 3 — Non-custodial paper trading (stretch; mirrors Invsto's model)
`Broker` interface with an **Alpaca paper-trading** adapter; promote a strategy to live paper signals; positions/PnL endpoints; fill reconciliation + audit log. **Paper only — never live.**

---

## 9. Suggested repo layout

```
strat-engine/
├── docker-compose.yml
├── Dockerfile
├── .github/workflows/ci.yml
├── pyproject.toml
├── README.md
├── manage.py
├── config/                 # Django settings, urls, celery (P2)
├── data/                   # committed OHLCV CSV fixtures
├── apps/
│   ├── strategies/         # Strategy model, rule grammar, serializers, views
│   ├── backtests/          # Backtest/Result models, API
│   └── core/               # auth, pagination, health, common
├── engine/                 # framework-free, importable on its own
│   ├── datasource.py       # DataSource interface + CSV/yfinance impls
│   ├── indicators.py       # registry over `ta`
│   ├── rules.py            # operand/operator registry + evaluator
│   ├── backtester.py       # vectorized, look-ahead-safe core
│   ├── costs.py            # fees + slippage
│   └── metrics.py          # QuantStats wrappers + tearsheet
├── brokers/                # Broker interface + paper/alpaca (P3)
└── tests/                  # incl. test_no_lookahead.py (headline)
```
Keep `engine/` import-free of Django so it's unit-testable and reusable.

---

## 10. Definition of done (Phase 1)
- [ ] `docker-compose up` → working API locally
- [ ] Public live-demo URL with a seeded, runnable backtest + tearsheet
- [ ] Look-ahead invariant test, idempotency test, known-answer test all passing in CI
- [ ] README with architecture diagram, correctness guarantees, measured metrics, curl examples, and limitations
- [ ] Clean commit history; meaningful messages

---

## 11. How to talk about it (for the application)
- **Resume line:** *"Built a Django REST Framework + PostgreSQL strategy-backtesting backend with a rule-based entry/exit engine (`ta`, `QuantStats`); guarantees no look-ahead bias via a property test, models fees/slippage, and runs idempotent, reproducible backtests — Dockerized with CI and a live demo."*
- **Cold-email hook (don't over-claim):** you studied their strategy-research surface and built a production Django/Postgres backend for it, with the correctness rigor a quant cares about (look-ahead-safe, costs, out-of-sample). Link the live demo + repo. Bridge to your BlueStock trading-platform experience. Do **not** mention your university.
- **Lead with BlueStock** in the application; this project is the proof-of-depth follow-up, not the headline.

---

## 12. Out of scope / do not do
- No real-money trading or live broker orders — ever.
- No AI/LLM/ML components.
- Don't hard-code strategies or indicators into the API layer — use the registries.
- Don't fabricate performance — real-ish data, real costs, no look-ahead.
- Don't begin Phase 2/3 until Phase 1 is tested, committed, and deployed.
