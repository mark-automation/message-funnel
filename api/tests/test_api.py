"""MessageFunnel API test suite — auth, connections, inbox, webhooks.

Run:  python -m pytest api/tests -q
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

# Isolated data dir per run BEFORE importing app modules.
_TMP = Path(__file__).resolve().parent.parent.parent / "data-test"
os.environ["MF_DATA_DIR"] = str(_TMP)
os.environ["MF_SECRET"] = "test-secret-key-for-ci-only"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402

client = TestClient(app)


def _unique_email() -> str:
    return f"test_{uuid.uuid4().hex[:8]}@example.com"


def _register_and_login():
    email = _unique_email()
    r = client.post("/api/auth/register", json={
        "email": email, "password": "hunter2secret", "display_name": "Tester",
    })
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    return email, {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Health + auth
# ---------------------------------------------------------------------------
def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "telegram" in body["platforms"]


def test_register_login_me():
    email, _ = _register_and_login()
    r = client.post("/api/auth/login", json={"email": email, "password": "hunter2secret"})
    assert r.status_code == 200
    token = r.json()["token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == email


def test_register_duplicate_email():
    email, _ = _register_and_login()
    r = client.post("/api/auth/register", json={
        "email": email, "password": "anotherpass1",
    })
    assert r.status_code == 409


def test_short_password_rejected():
    r = client.post("/api/auth/register", json={
        "email": _unique_email(), "password": "short",
    })
    assert r.status_code == 422


def test_wrong_password():
    email, _ = _register_and_login()
    r = client.post("/api/auth/login", json={"email": email, "password": "wrongpassword"})
    assert r.status_code == 401


def test_protected_endpoint_requires_token():
    r = client.get("/api/conversations")
    assert r.status_code in (401, 403)
    r = client.get("/api/conversations", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------
def test_platforms_listed():
    r = client.get("/api/platforms")
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()}
    assert {"messenger", "instagram", "tiktok", "whatsapp", "telegram", "x"} <= ids


def test_connection_crud_roundtrip():
    _, auth = _register_and_login()
    # create
    r = client.put("/api/connections/telegram", headers=auth, json={
        "handle": "@my_bot",
        "credentials": {"bot_token": "123456:ABC-secret-token-value"},
    })
    assert r.status_code == 200, r.text
    conn = r.json()
    assert conn["platform"] == "telegram"
    assert conn["handle"] == "@my_bot"
    # credentials must never come back raw
    assert "ABC-secret" not in r.text
    assert conn["masked"]["bot_token"].endswith("alue") or "••••" in conn["masked"]["bot_token"]
    cid = conn["id"]
    # list
    r = client.get("/api/connections", headers=auth)
    assert len(r.json()) == 1
    # update (upsert same platform)
    r = client.put("/api/connections/telegram", headers=auth, json={
        "handle": "@renamed_bot", "credentials": {"bot_token": "999:NEW"},
    })
    assert r.status_code == 200
    r = client.get("/api/connections", headers=auth)
    conns = r.json()
    assert len(conns) == 1 and conns[0]["handle"] == "@renamed_bot"
    # test endpoint
    r = client.post(f"/api/connections/{cid}/test", headers=auth)
    body = r.json()
    assert body["ok"] is True
    # delete
    r = client.delete(f"/api/connections/{cid}", headers=auth)
    assert r.status_code == 200
    assert client.get("/api/connections", headers=auth).json() == []


def test_unknown_platform_rejected():
    _, auth = _register_and_login()
    r = client.put("/api/connections/beeper", headers=auth,
                   json={"credentials": {"x": "y"}})
    assert r.status_code == 404


def test_connections_are_user_scoped():
    _, auth_a = _register_and_login()
    _, auth_b = _register_and_login()
    r = client.put("/api/connections/x", headers=auth_a, json={
        "credentials": {"api_key": "aaa", "api_secret": "bbb",
                        "oauth_token": "ccc", "oauth_token_secret": "ddd"},
    })
    cid = r.json()["id"]
    # user B cannot see or delete A's connection
    assert all(c["id"] != cid for c in client.get("/api/connections", headers=auth_b).json())
    assert client.delete(f"/api/connections/{cid}", headers=auth_b).status_code == 404


# ---------------------------------------------------------------------------
# Inbox + webhook ingest
# ---------------------------------------------------------------------------
def _ingest(auth, platform, payload, **params):
    return client.post(f"/api/webhooks/{platform}", headers=auth,
                       params=params or {}, json={"payload": payload})


def _connect(auth, platform, creds, handle=""):
    r = client.put(f"/api/connections/{platform}", headers=auth,
                   json={"handle": handle, "credentials": creds})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_webhook_ingest_and_inbox_flow():
    _, auth = _register_and_login()
    conn_id = _connect(auth, "telegram", {"bot_token": "tok"}, handle="@t")

    payload = {"sender": "Nadine Uy", "text": "Do you ship to Cebu?"}
    r = _ingest(auth, "telegram", payload, conn=conn_id)
    assert r.status_code == 200 and r.json()["received"] == 1

    convs = client.get("/api/conversations", headers=auth).json()
    assert len(convs) == 1
    conv = convs[0]
    assert conv["platform"] == "telegram" and conv["unread_count"] == 1

    msgs = client.get(f"/api/conversations/{conv['id']}/messages", headers=auth).json()
    assert msgs[0]["text"] == "Do you ship to Cebu?" and msgs[0]["direction"] == "in"

    # Reply
    r = client.post(f"/api/conversations/{conv['id']}/messages", headers=auth,
                    json={"text": "Yes po! J&T 2-3 days."})
    assert r.status_code == 200 and r.json()["direction"] == "out"

    # Mark read
    r = client.post(f"/api/conversations/{conv['id']}/read", headers=auth)
    assert r.json()["unread_count"] == 0
    convs = client.get("/api/conversations?unread_only=true", headers=auth).json()
    assert convs == []


def test_meta_webhook_normalization():
    _, auth = _register_and_login()
    conn_id = _connect(auth, "messenger",
                       {"page_access_token": "pt", "page_id": "1", "app_secret": "s"})
    payload = {
        "object": "page",
        "entry": [{
            "id": "PAGE1",
            "messaging": [{
                "sender": {"id": "USER42"},
                "message": {"mid": "m1", "text": "Hi! Is this available?"},
            }],
        }],
    }
    r = _ingest(auth, "messenger", payload, conn=conn_id)
    assert r.json()["received"] == 1
    convs = client.get("/api/conversations?platform=messenger", headers=auth).json()
    assert len(convs) == 1 and convs[0]["platform"] == "messenger"


def test_meta_verification_handshake():
    r = client.get("/api/webhooks/messenger",
                   params={"hub.mode": "subscribe", "hub.verify_token": "v",
                           "hub.challenge": "1234567"})
    assert r.status_code == 200
    assert int(r.text) == 1234567


def test_webhook_without_matching_connection_404():
    _, auth = _register_and_login()
    r = _ingest(auth, "tiktok", {"text": "hello"})
    assert r.status_code == 404


def test_unread_counts_accumulate_per_event():
    _, auth = _register_and_login()
    conn_id = _connect(auth, "whatsapp", {"access_token": "t"})
    for i in range(3):
        r = _ingest(auth, "whatsapp", {"sender": "Paolo", "text": f"msg {i}"}, conn=conn_id)
        assert r.status_code == 200, r.text
    convs = client.get("/api/conversations", headers=auth).json()
    assert convs[0]["unread_count"] == 3


def test_users_cannot_see_each_others_conversations():
    _, auth_a = _register_and_login()
    _, auth_b = _register_and_login()
    client.put("/api/connections/telegram", headers=auth_a,
               json={"credentials": {"bot_token": "t"}})
    _ingest(auth_a, "telegram", {"sender": "X", "text": "for A only"})
    assert client.get("/api/conversations", headers=auth_b).json() == []
