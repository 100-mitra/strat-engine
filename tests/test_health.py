"""Phase 0 skeleton tests: liveness, engine import, and the token-auth stack."""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient


def test_healthz_returns_ok():
    client = APIClient()
    resp = client.get("/healthz/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "stratengine"
    assert "version" in body


def test_healthz_requires_no_auth():
    # Liveness must not be gated behind authentication.
    resp = APIClient().get("/healthz/")
    assert resp.status_code == 200


def test_index_landing_page():
    resp = APIClient().get("/")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/html")
    body = resp.content.decode()
    assert "StratEngine" in body
    assert "/api/auth/token/" in body


def test_engine_version_importable():
    from engine import ENGINE_VERSION

    assert isinstance(ENGINE_VERSION, str) and ENGINE_VERSION


@pytest.mark.django_db
def test_obtain_auth_token():
    User.objects.create_user(username="alice", password="s3cret-pw-123")
    resp = APIClient().post(
        "/api/auth/token/", {"username": "alice", "password": "s3cret-pw-123"}, format="json"
    )
    assert resp.status_code == 200
    assert resp.json().get("token")


@pytest.mark.django_db
def test_obtain_auth_token_bad_credentials():
    resp = APIClient().post(
        "/api/auth/token/", {"username": "nope", "password": "wrong"}, format="json"
    )
    assert resp.status_code == 400
