"""MessageFunnel API — unified inbox backend with auth + account connections.

One REST surface over every messaging platform. Users register, log in
(JWT Bearer), and connect their messaging accounts in one place; every
platform's messages funnel into a single normalized inbox.

Run:  uvicorn api.main:app --host 0.0.0.0 --port 8800   (docs at /docs)
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from . import connectors as cx
from . import db, security

app = FastAPI(title="MessageFunnel API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Pages origin(s); tighten when API host is fixed
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Auth dependency + models
# ---------------------------------------------------------------------------
def current_user(
    cred: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> Dict[str, Any]:
    if cred is None:
        raise HTTPException(401, "Missing bearer token")
    uid = security.decode_token(cred.credentials)
    if uid is None:
        raise HTTPException(401, "Invalid or expired token")
    user = db.get_user_by_id(uid)
    if user is None:
        raise HTTPException(401, "Unknown user")
    return user


class RegisterBody(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str = ""


class LoginBody(BaseModel):
    email: str
    password: str


class ConnectionBody(BaseModel):
    handle: str = ""
    credentials: Dict[str, Any]


class SendBody(BaseModel):
    text: str


class WebhookBody(BaseModel):
    payload: Dict[str, Any]


def _auth_payload(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "token": security.create_token(user["id"]),
        "token_type": "bearer",
        "expires_in": security.TOKEN_TTL_SECONDS,
        "user": {"id": user["id"], "email": user["email"],
                 "display_name": user["display_name"]},
    }


# ---------------------------------------------------------------------------
# Health + auth endpoints
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "service": "message-funnel", "time": time.time(),
            "version": app.version, "platforms": sorted(cx.PLATFORMS)}


@app.post("/api/auth/register", status_code=201)
def register(body: RegisterBody) -> Dict[str, Any]:
    if db.get_user_by_email(body.email):
        raise HTTPException(409, "Email already registered")
    user = db.create_user(body.email, body.password,
                          body.display_name or body.email.split("@")[0])
    return _auth_payload(user)


@app.post("/api/auth/login")
def login(body: LoginBody) -> Dict[str, Any]:
    user = db.get_user_by_email(body.email)
    if not user or not security.verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    return _auth_payload(user)


@app.get("/api/auth/me")
def me(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    return {"id": user["id"], "email": user["email"], "display_name": user["display_name"]}


# ---------------------------------------------------------------------------
# Account connections (all platform credentials in one place)
# ---------------------------------------------------------------------------
CREDENTIAL_FIELDS: Dict[str, List[str]] = {
    # What each platform's connection form collects. OAuth flows replace this later.
    "messenger": ["page_access_token", "page_id", "app_secret"],
    "instagram": ["access_token", "account_id", "app_secret"],
    "tiktok": ["access_key", "access_secret", "business_id"],
    "whatsapp": ["access_token", "phone_number_id", "waba_id"],
    "telegram": ["bot_token"],
    "x": ["api_key", "api_secret", "oauth_token", "oauth_token_secret"],
}


@app.get("/api/platforms")
def platforms() -> List[Dict[str, Any]]:
    return [
        {"id": pid, "name": meta["name"], "color": meta["color"],
         "credential_fields": CREDENTIAL_FIELDS.get(pid, ["access_token"]),
         "connected": False}
        for pid, meta in cx.PLATFORMS.items()
    ]


@app.get("/api/connections")
def list_connections(user: Dict[str, Any] = Depends(current_user)) -> List[Dict[str, Any]]:
    return [db.public_connection(r) for r in db.list_connections(user["id"])]


@app.put("/api/connections/{platform}")
def upsert_connection(
    platform: str, body: ConnectionBody,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    if platform not in cx.PLATFORMS:
        raise HTTPException(404, f"Unknown platform '{platform}'")
    row = db.upsert_connection(user["id"], platform, body.handle.strip(), body.credentials)
    return db.public_connection(row)


@app.delete("/api/connections/{conn_id}")
def delete_connection(conn_id: int,
                      user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    if not db.delete_connection(user["id"], conn_id):
        raise HTTPException(404, "Connection not found")
    return {"deleted": conn_id}


@app.post("/api/connections/{conn_id}/test")
def test_connection(conn_id: int,
                    user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    """Verify stored credential completeness (live ping lands with real adapters)."""
    row = db.get_connection(user["id"], conn_id)
    if not row:
        raise HTTPException(404, "Connection not found")
    creds = security.decrypt_credentials(row["credentials_enc"])
    missing = [f for f in CREDENTIAL_FIELDS.get(row["platform"], []) if f not in creds]
    if missing:
        return {"ok": False, "reason": f"missing fields: {', '.join(missing)}"}
    return {"ok": True, "reason": "credentials complete — live verify lands with real adapter"}


# ---------------------------------------------------------------------------
# Unified inbox (per-user, DB-backed)
# ---------------------------------------------------------------------------
@app.get("/api/accounts")
def accounts(user: Dict[str, Any] = Depends(current_user)) -> List[Dict[str, Any]]:
    conns = {c["platform"]: c for c in db.list_connections(user["id"])}
    out = []
    for pid, meta in cx.PLATFORMS.items():
        c = conns.get(pid)
        out.append({
            "platform": pid, "display_name": meta["name"], "color": meta["color"],
            "handle": c["handle"] if c else "",
            "connected": c is not None,
            "connection_id": c["id"] if c else None,
        })
    return out


@app.get("/api/conversations")
def conversations(
    platform: Optional[str] = Query(None),
    unread_only: bool = Query(False),
    user: Dict[str, Any] = Depends(current_user),
) -> List[Dict[str, Any]]:
    convs = db.list_conversations(user["id"], platform=platform, unread_only=unread_only)
    for c in convs:
        c["meta"] = cx.PLATFORMS[c["platform"]]
    return convs


@app.get("/api/conversations/{conv_id}/messages")
def messages(conv_id: int, user: Dict[str, Any] = Depends(current_user)) -> List[Dict[str, Any]]:
    conv = db.get_conversation(user["id"], conv_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return db.list_messages(conv_id)


@app.post("/api/conversations/{conv_id}/read")
def mark_read(conv_id: int, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    if not db.mark_read(user["id"], conv_id):
        raise HTTPException(404, "Conversation not found")
    return {"ok": True, "id": conv_id, "unread_count": 0}


@app.post("/api/conversations/{conv_id}/messages")
def send(conv_id: int, body: SendBody,
         user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    conv = db.get_conversation(user["id"], conv_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "empty message")
    msg = db.append_message(conv_id, conv["platform"], "You", text[:4000], "out")
    return msg


# ---------------------------------------------------------------------------
# Webhooks — per-connection ingest. Route by connection id (?conn=<id> /
# x-mf-conn header); falls back to ?user=<email> for the first matching
# connection. Signature verification per platform arrives with real adapters.
# ---------------------------------------------------------------------------
@app.get("/api/webhooks/{platform}")
async def webhook_verify(platform: str, request: Request) -> Any:
    _ = platform
    challenge = request.query_params.get("hub.challenge", "")
    return int(challenge) if challenge.isdigit() else challenge


def _resolve_webhook_target(platform: str, request: Request) -> Optional[Dict[str, Any]]:
    """Find the (user, connection) a webhook event belongs to."""
    conn_param = request.headers.get("x-mf-conn") or request.query_params.get("conn")
    if conn_param and conn_param.isdigit():
        row = db.get_conn().execute(
            "SELECT * FROM connections WHERE id=? AND platform=?",
            (int(conn_param), platform),
        ).fetchone()
        if row:
            user = db.get_user_by_id(row["user_id"])
            if user:
                return {"user": user, "connection": dict(row)}
        return None
    user_email = request.headers.get("x-mf-user") or request.query_params.get("user", "")
    user = db.get_user_by_email(user_email) if user_email else None
    if not user:
        return None
    conn = db.get_connection_by_platform(user["id"], platform)
    if not conn:
        return None
    return {"user": user, "connection": conn}


def _ingest(target: Dict[str, Any], msgs: List[Dict[str, Any]]) -> int:
    conn = target["connection"]
    for m in msgs:
        cid = db.resolve_conversation(
            conn["id"], target["user"]["id"], m["platform"],
            m.pop("external_ref"), m["sender_name"],
        )
        db.append_message(cid, m["platform"], m["sender_name"],
                          m["text"], m["direction"], m["timestamp"])
    return len(msgs)


@app.post("/api/webhooks/{platform}")
def webhook_receive(platform: str, body: WebhookBody, request: Request) -> Dict[str, Any]:
    if platform not in cx.PLATFORMS:
        raise HTTPException(404, f"Unknown platform '{platform}'")
    target = _resolve_webhook_target(platform, request)
    if target is None:
        raise HTTPException(404, "No connection matches this webhook — set ?conn=<id>")

    def resolve_conv(p: str, ext_id: str, name: str) -> str:
        # Connectors treat the returned value as conversation id; we carry the
        # external ref through and resolve per-user at ingest time instead.
        return ext_id

    if platform in ("messenger", "instagram"):
        raw = cx.normalize_meta_webhook(body.payload, resolve_conv)
    elif platform == "tiktok":
        raw = cx.normalize_tiktok_webhook(body.payload, resolve_conv)
    else:
        raw = cx.CONNECTORS[platform].parse_webhook(body.payload, resolve_conv)
    # Attach external_ref from resolve result (connector used it as cid).
    for m in raw:
        m["external_ref"] = m.pop("conversation_id") or m["sender_name"]
    received = _ingest(target, raw)
    return {"received": received}


# ---------------------------------------------------------------------------
# Static frontend (same origin as the API — no CORS friction, Pages mirrors it)
# Mounted last so /api/* routes win.
# ---------------------------------------------------------------------------
from pathlib import Path as _Path

from fastapi.staticfiles import StaticFiles as _StaticFiles

_STATIC = _Path(__file__).resolve().parent.parent
if (_STATIC / "index.html").exists():
    app.mount("/", _StaticFiles(directory=_STATIC, html=True), name="ui")
