"""Unified message schema + platform connector registry.

Every platform (real or mock) is normalized into this shape so the
frontend renders one inbox regardless of source.

Real-platform notes (v2, needs Dan's developer accounts):
- Messenger / Instagram DMs -> Meta: App ID + App Secret + Page Access Token,
  webhooks at https://graph.facebook.com vX. Subscription: messages, messaging_postbacks.
- TikTok -> Business Messaging API (approval required), webhook callback + signature.
Until those credentials exist, MockConnector serves deterministic demo traffic and
Meta/TikTok adapters normalize webhook payloads (so the ingest path is testable now).
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Platform registry (id -> display metadata used by API + frontend badges)
# ---------------------------------------------------------------------------
PLATFORMS: Dict[str, Dict[str, str]] = {
    "messenger": {"name": "Messenger", "color": "#0084FF", "glyph": "M"},
    "instagram": {"name": "Instagram", "color": "#E1306C", "glyph": "IG"},
    "tiktok":    {"name": "TikTok",    "color": "#FE2C55", "glyph": "TT"},
    "whatsapp":  {"name": "WhatsApp",  "color": "#25D366", "glyph": "WA"},
    "telegram":  {"name": "Telegram",  "color": "#229ED9", "glyph": "TG"},
    "x":         {"name": "X / DMs",   "color": "#8899A6", "glyph": "X"},
}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def normalize_message(
    *,
    platform: str,
    conversation_id: str,
    sender_name: str,
    text: str,
    direction: str = "in",
    ts: Optional[float] = None,
) -> Dict[str, Any]:
    """Map any platform event into the unified message dict."""
    return {
        "id": new_id("msg"),
        "conversation_id": conversation_id,
        "platform": platform,
        "sender_name": sender_name,
        "text": text,
        "direction": direction,  # "in" | "out"
        "timestamp": ts if ts is not None else time.time(),
    }


# ---------------------------------------------------------------------------
# Webhook normalizers (ingest path works before real tokens exist)
# ---------------------------------------------------------------------------
def _meta_sender_name(entry: Dict[str, Any]) -> str:
    contact = entry.get("contacts") or [{}]
    return contact[0].get("profile_name") or f"user_{entry.get('id', 'unknown')}"


def normalize_meta_webhook(payload: Dict[str, Any], resolve_conv) -> List[Dict[str, Any]]:
    """Normalize Messenger/Instagram webhook payloads (Messaging/Webhook v-graph).

    resolve_conv(platform, external_user_id, display_name) -> conversation_id
    """
    out: List[Dict[str, Any]] = []
    object_type = str(payload.get("object", "page"))
    platform = "instagram" if object_type == "instagram" else "messenger"
    for entry in payload.get("entry", []):
        sender_name = _meta_sender_name(entry)
        for event in entry.get("messaging", []):
            msg = event.get("message") or {}
            text = msg.get("text")
            if not text:
                continue
            ext_id = str(event.get("sender", {}).get("id", "unknown"))
            cid = resolve_conv(platform, ext_id, sender_name)
            out.append(normalize_message(
                platform=platform, conversation_id=cid,
                sender_name=sender_name, text=text,
            ))
    return out


def normalize_tiktok_webhook(payload: Dict[str, Any], resolve_conv) -> List[Dict[str, Any]]:
    """Best-effort TikTok webhook normalization (Business Messaging shape varies).

    Accepts {event|data:{conversation_id/sender/open_id, content/message/text}}.
    """
    body = payload.get("event") or payload.get("data") or payload
    text = body.get("content") or body.get("message") or body.get("text")
    if not isinstance(text, str):
        return []
    sender_name = body.get("nickname") or body.get("sender_nickname") or "tiktok_user"
    ext_id = str(body.get("open_id") or body.get("conversation_id") or body.get("sender_id") or "unknown")
    cid = resolve_conv("tiktok", ext_id, sender_name)
    return [normalize_message(
        platform="tiktok", conversation_id=cid,
        sender_name=sender_name, text=text,
    )]


# ---------------------------------------------------------------------------
# Connector interface
# ---------------------------------------------------------------------------
class Connector:
    """Per-platform adapter contract. Mock fills everything; real adapters
    implement fetch_* against the vendor API using env credentials."""

    id = "base"

    def list_conversations(self, store) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def send_message(self, store, conversation_id: str, text: str) -> Dict[str, Any]:
        raise NotImplementedError

    def parse_webhook(self, payload: Dict[str, Any], resolve_conv) -> List[Dict[str, Any]]:
        raise NotImplementedError


class MockConnector(Connector):
    """Serves the seeded in-memory store. Swap for real adapters per platform
    when developer-app credentials are provisioned."""

    def __init__(self, platform_id: str):
        self.id = platform_id

    def list_conversations(self, store) -> List[Dict[str, Any]]:
        return [c for c in store["conversations"].values() if c["platform"] == self.id]

    def send_message(self, store, conversation_id: str, text: str) -> Dict[str, Any]:
        conv = store["conversations"][conversation_id]
        msg = normalize_message(
            platform=conv["platform"], conversation_id=conversation_id,
            sender_name="You", text=text, direction="out",
        )
        store["messages"].setdefault(conversation_id, []).append(msg)
        conv["updated_at"] = msg["timestamp"]
        conv["last_message"] = text
        return msg

    def parse_webhook(self, payload: Dict[str, Any], resolve_conv) -> List[Dict[str, Any]]:
        # Generic mock ingest: {"sender":"Name","text":"hi"} or full normalized form.
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return []
        sender = str(payload.get("sender") or "webhook_user")
        cid = resolve_conv(self.id, sender.lower().replace(" ", "_"), sender)
        return [normalize_message(
            platform=self.id, conversation_id=cid, sender_name=sender, text=text,
        )]


class MetaStubConnector(Connector):
    """Messenger/Instagram adapter skeleton. Fetches require META_PAGE_TOKEN +
    META_APP_SECRET (env); webhook normalization already works today."""

    id = "meta-stub"
    requires = ["META_PAGE_TOKEN", "META_APP_SECRET", "META_VERIFY_TOKEN"]

    def list_conversations(self, store):
        raise RuntimeError(
            "Meta connector not provisioned: set "
            f"{', '.join(self.requires)} and implement Graph API paging."
        )

    def send_message(self, store, conversation_id, text):
        raise RuntimeError("Meta connector not provisioned.")

    def parse_webhook(self, payload, resolve_conv):
        return normalize_meta_webhook(payload, resolve_conv)


CONNECTORS: Dict[str, Connector] = {
    pid: MockConnector(pid) for pid in PLATFORMS
}


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "user"
