"""Backtest API: run, idempotent caching, equity-curve, tearsheet, OOS, owner isolation."""

import pytest

pytestmark = pytest.mark.django_db


def test_run_backtest_returns_done_with_metrics(auth_client, create_strategy):
    sid = create_strategy()
    resp = auth_client.post("/api/backtests/", {"strategy": sid}, format="json")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["status"] == "done"
    assert body["cached"] is False
    assert body["result_hash"]
    assert body["metrics"]["periods_per_year"] == 252
    for key in ("cagr", "sharpe", "max_drawdown", "num_trades"):
        assert key in body["metrics"]


def test_identical_run_is_cached(auth_client, create_strategy):
    sid = create_strategy()
    first = auth_client.post("/api/backtests/", {"strategy": sid}, format="json").json()
    second = auth_client.post("/api/backtests/", {"strategy": sid}, format="json").json()
    # New row (audit trail) but reused computation.
    assert second["id"] != first["id"]
    assert second["cached"] is True
    assert second["source_backtest_id"] == first["id"]
    assert second["result_hash"] == first["result_hash"]
    assert second["metrics"] == first["metrics"]


def test_changing_params_is_not_cached(auth_client, create_strategy):
    sid = create_strategy()
    a = auth_client.post("/api/backtests/", {"strategy": sid, "fees_bps": 5}, format="json").json()
    b = auth_client.post("/api/backtests/", {"strategy": sid, "fees_bps": 25}, format="json").json()
    assert b["cached"] is False
    assert a["result_hash"] != b["result_hash"]


def test_equity_curve_endpoint(auth_client, create_strategy):
    sid = create_strategy()
    bid = auth_client.post(
        "/api/backtests/", {"strategy": sid, "oos_split_date": "2022-01-01"}, format="json"
    ).json()["id"]
    resp = auth_client.get(f"/api/backtests/{bid}/equity-curve/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["oos_boundary_date"] == "2022-01-01"
    assert len(body["points"]) > 100
    point = body["points"][0]
    assert set(point) == {"date", "equity", "region"}
    assert {p["region"] for p in body["points"]} == {"in_sample", "out_of_sample"}


def test_oos_split_metrics(auth_client, create_strategy):
    sid = create_strategy()
    body = auth_client.post(
        "/api/backtests/", {"strategy": sid, "oos_split_date": "2022-01-01"}, format="json"
    ).json()
    assert "oos" in body["metrics"]
    assert "in_sample" in body["metrics"]["oos"]
    assert "out_of_sample" in body["metrics"]["oos"]


def test_tearsheet_endpoint_returns_html(auth_client, create_strategy):
    sid = create_strategy()
    bid = auth_client.post("/api/backtests/", {"strategy": sid}, format="json").json()["id"]
    resp = auth_client.get(f"/api/backtests/{bid}/tearsheet/")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/html")
    assert b"<html" in resp.content.lower()


def test_cannot_run_on_another_users_strategy(
    make_client, user, other_user, valid_strategy_payload
):
    alice = make_client(user)
    bob = make_client(other_user)
    sid = alice.post("/api/strategies/", valid_strategy_payload, format="json").json()["id"]
    # Bob references Alice's strategy id -> scoped queryset rejects it as invalid (400).
    resp = bob.post("/api/backtests/", {"strategy": sid}, format="json")
    assert resp.status_code == 400


def test_backtest_owner_isolation(make_client, user, other_user, valid_strategy_payload):
    alice = make_client(user)
    bob = make_client(other_user)
    sid = alice.post("/api/strategies/", valid_strategy_payload, format="json").json()["id"]
    bid = alice.post("/api/backtests/", {"strategy": sid}, format="json").json()["id"]
    assert bob.get(f"/api/backtests/{bid}/").status_code == 404


def test_symbol_not_in_universe_400(auth_client, create_strategy):
    sid = create_strategy()
    resp = auth_client.post(
        "/api/backtests/", {"strategy": sid, "symbol": "BTC-USD"}, format="json"
    )
    assert resp.status_code == 400


def test_run_requires_auth(create_strategy):
    from rest_framework.test import APIClient

    sid = create_strategy()
    resp = APIClient().post("/api/backtests/", {"strategy": sid}, format="json")
    assert resp.status_code in (401, 403)
