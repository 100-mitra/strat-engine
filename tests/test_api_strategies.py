"""Strategy API: auth, CRUD, owner isolation, version bump, pagination, and the 400 matrix."""

import copy

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_list_requires_auth():
    resp = APIClient().get("/api/strategies/")
    assert resp.status_code in (401, 403)


def test_create_and_retrieve(auth_client, valid_strategy_payload):
    resp = auth_client.post("/api/strategies/", valid_strategy_payload, format="json")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["version"] == 1
    assert body["universe"] == ["SPY"]

    got = auth_client.get(f"/api/strategies/{body['id']}/")
    assert got.status_code == 200
    assert got.json()["name"] == valid_strategy_payload["name"]


def test_patch_bumps_version(auth_client, create_strategy):
    sid = create_strategy()
    resp = auth_client.patch(f"/api/strategies/{sid}/", {"name": "renamed"}, format="json")
    assert resp.status_code == 200
    assert resp.json()["version"] == 2
    assert resp.json()["name"] == "renamed"


def test_owner_isolation_returns_404(make_client, user, other_user, valid_strategy_payload):
    alice = make_client(user)
    bob = make_client(other_user)
    sid = alice.post("/api/strategies/", valid_strategy_payload, format="json").json()["id"]
    # Bob cannot see Alice's strategy — 404 (existence not leaked), not 403.
    assert bob.get(f"/api/strategies/{sid}/").status_code == 404
    assert bob.patch(f"/api/strategies/{sid}/", {"name": "x"}, format="json").status_code == 404
    # And Bob's list is empty.
    assert bob.get("/api/strategies/").json()["count"] == 0


def test_pagination(auth_client, valid_strategy_payload):
    for i in range(25):
        payload = {**valid_strategy_payload, "name": f"s{i}"}
        assert auth_client.post("/api/strategies/", payload, format="json").status_code == 201
    page1 = auth_client.get("/api/strategies/").json()
    assert page1["count"] == 25
    assert len(page1["results"]) == 20  # PAGE_SIZE
    assert page1["next"] is not None


# --- the 400 validation matrix -------------------------------------------------
def _with_rules(payload, rules):
    p = copy.deepcopy(payload)
    p["rules"] = rules
    return p


def _simple_entry(condition):
    return {
        "entry": {"logic": "AND", "conditions": [condition]},
        "exit": {"logic": "AND", "conditions": [condition]},
    }


@pytest.mark.parametrize(
    "bad_rules_builder",
    [
        # empty conditions
        lambda: {
            "entry": {"logic": "AND", "conditions": []},
            "exit": {"logic": "AND", "conditions": []},
        },
        # unknown indicator
        lambda: _simple_entry(
            {
                "left": {"type": "indicator", "name": "BOLLINGER", "params": {"window": 20}},
                "operator": ">",
                "right": {"type": "price", "field": "close"},
            }
        ),
        # unknown operator
        lambda: _simple_entry(
            {
                "left": {"type": "price", "field": "close"},
                "operator": "≈",
                "right": {"type": "value", "value": 1},
            }
        ),
        # bad price field
        lambda: _simple_entry(
            {
                "left": {"type": "price", "field": "bid"},
                "operator": ">",
                "right": {"type": "value", "value": 1},
            }
        ),
        # non-positive window
        lambda: _simple_entry(
            {
                "left": {"type": "indicator", "name": "SMA", "params": {"window": 0}},
                "operator": ">",
                "right": {"type": "price", "field": "close"},
            }
        ),
        # value vs value (no market dependency)
        lambda: _simple_entry(
            {
                "left": {"type": "value", "value": 1},
                "operator": ">",
                "right": {"type": "value", "value": 2},
            }
        ),
        # unexpected operand field
        lambda: _simple_entry(
            {
                "left": {"type": "price", "field": "close", "bogus": 1},
                "operator": ">",
                "right": {"type": "value", "value": 1},
            }
        ),
        # missing 'exit' group
        lambda: {"entry": {"logic": "AND", "conditions": []}},
    ],
)
def test_rule_validation_returns_400(auth_client, valid_strategy_payload, bad_rules_builder):
    payload = _with_rules(valid_strategy_payload, bad_rules_builder())
    resp = auth_client.post("/api/strategies/", payload, format="json")
    assert resp.status_code == 400, resp.content


def test_unknown_universe_symbol_400(auth_client, valid_strategy_payload):
    payload = {**valid_strategy_payload, "universe": ["NOPE"]}
    resp = auth_client.post("/api/strategies/", payload, format="json")
    assert resp.status_code == 400


def test_bad_position_sizing_400(auth_client, valid_strategy_payload):
    payload = {
        **valid_strategy_payload,
        "position_sizing": {"type": "fixed_fraction", "fraction": 5},
    }
    resp = auth_client.post("/api/strategies/", payload, format="json")
    assert resp.status_code == 400
