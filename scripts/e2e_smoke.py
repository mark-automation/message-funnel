"""End-to-end smoke test against a running MessageFunnel API.

Usage: python scripts/e2e_smoke.py [base_url]
"""
from __future__ import annotations

import json
import random
import string
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8811"


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=15)
    email = "e2e_" + "".join(random.choices(string.ascii_lowercase, k=8)) + "@mf.test"

    r = c.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok", r.text
    print("health OK")

    r = c.post("/api/auth/register", json={
        "email": email, "password": "passw0rd123", "display_name": "E2E Dan"})
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    print(f"register+token OK ({email})")

    r = c.put("/api/connections/messenger", headers=h, json={
        "handle": "Dan's Page",
        "credentials": {"page_access_token": "EAAG-secret", "page_id": "111",
                        "app_secret": "shh"}})
    assert r.status_code == 200, r.text
    conn = r.json()
    assert "EAAG-secret" not in json.dumps(conn), "credential leaked!"
    cid = conn["id"]
    print(f"connection OK id={cid} masked={conn['masked']}")

    payload = {"object": "page", "entry": [{
        "id": "P1",
        "messaging": [{"sender": {"id": "U9"},
                       "message": {"text": "Hello po, ask lang ako"}}]}]}
    r = c.post(f"/api/webhooks/messenger?conn={cid}", headers=h,
               json={"payload": payload})
    assert r.status_code == 200 and r.json()["received"] == 1, r.text
    print("webhook ingest OK")

    convs = c.get("/api/conversations", headers=h).json()
    assert len(convs) == 1 and convs[0]["unread_count"] == 1, convs
    vid = convs[0]["id"]
    print(f"inbox OK: conversation {vid} from '{convs[0]['title']}'")

    r = c.post(f"/api/conversations/{vid}/messages", headers=h,
               json={"text": "Hi! How can we help?"})
    assert r.status_code == 200 and r.json()["direction"] == "out", r.text

    msgs = c.get(f"/api/conversations/{vid}/messages", headers=h).json()
    assert [m["direction"] for m in msgs] == ["in", "out"], msgs
    print("thread:", " -> ".join(f"{m['direction']}:{m['text'][:30]}" for m in msgs))

    r = c.get("/api/conversations?unread_only=true", headers=h)
    assert r.status_code == 200
    r = c.post(f"/api/conversations/{vid}/read", headers=h)
    assert r.json()["unread_count"] == 0
    assert c.get("/api/conversations?unread_only=true", headers=h).json() == []
    print("mark-read OK")

    r = c.post(f"/api/connections/{cid}/test", headers=h)
    assert r.json()["ok"] is True, r.text
    print("connection test OK")

    # wrong credentials rejected
    r = c.post("/api/auth/login", json={"email": email, "password": "wrong-pass-1"})
    assert r.status_code == 401
    print("bad login rejected OK")

    print("\nALL E2E CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
