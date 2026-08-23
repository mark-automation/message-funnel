"""MessageFunnel API — unified inbox backend.

One REST surface over every messaging platform. Frontend (GitHub Pages)
points at this service via config.js; until real platform credentials are
provisioned, mock connectors serve deterministic demo traffic.

Run:  uvicorn api.main:app --host 0.0.0.0 --port 8800
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from . import connectors as cx

app = FastAPI(title="MessageFunnel API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Pages origin(s); tighten when API host is fixed
    allow_methods=["*"],
    allow_headers=["*"],
)

STORE: Dict[str, Any] = {"conversations": {}, "messages": {}}


# ---------------------------------------------------------------------------
# Seed: deterministic demo traffic across all platforms (PH small-biz flavor)
# ---------------------------------------------------------------------------
SEED: List[Dict[str, Any]] = [
    # (platform, customer, ext_key, unread, [(dir_offset_min, direction, text), ...])
    ("messenger", "Maria Santos", "maria_santos", 2, [
        (58, "in", "Hi! Is the linen tote still available?"),
        (55, "out", "Yes po! Beige and black colors left."),
        (12, "in", "Order na ako ng 2. Pwede ba COD sa Cavite?"),
        (9,  "in", "Hello? Still there po?"),
    ]),
    ("messenger", "Jomar Dela Cruz", "jomar_dc", 0, [
        (240, "in", "Boss may stock kayo ng size 11?"),
        (236, "out", "Wala na sir, last ko size 10. Restock next week."),
        (230, "in", "Sige pa-reserve nga pag dumating."),
    ]),
    ("instagram", "bea.inthewild", "bea_itw", 1, [
        (95, "in", "saw your reel!! do you ship to Cebu? 🥺"),
        (90, "out", "Yes we do! J&T express, 2-3 days 🚚"),
        (18, "in", "yayyy sending a DM form na"),
    ]),
    ("instagram", "kevinlifts", "kevin_lifts", 0, [
        (400, "in", "bro that strap design is fire. collab tayo?"),
        (395, "out", "Send us a portfolio link, let's talk 💪"),
    ]),
    ("tiktok", "@lola.nena.shop", "lola_nena", 3, [
        (75, "in", "naka live ka ba mamaya? gusto ko yung bamboo bag"),
        (74, "in", "hello po??"),
        (70, "in", "sige bibili nalang ako sa shopee pag wala"),
    ]),
    ("tiktok", "@davaofoodtrip", "davao_ft", 0, [
        (300, "in", "pabili po ng 3 sampler box, ship sa Davao"),
        (295, "out", "Noted! Sending checkout link po."),
    ]),
    ("whatsapp", "Regine Aquino", "regine_aq", 1, [
        (140, "in", "Good pm, asking for wholesale price list"),
        (138, "out", "Sending po. 12pcs min per SKU for wholesale."),
        (30,  "in", "Got it, will forward to our buyer in Baguio ✅"),
    ]),
    ("whatsapp", "Paolo Reyes", "paolo_r", 0, [
        (500, "in", "Kuya, bayad na via GCash 🙏 confirm pls"),
        (498, "out", "Received po, salamat! Shipping tomorrow."),
    ]),
    ("telegram", "Nadine Uy", "nadine_uy", 0, [
        (700, "in", "Do you accept bulk orders for corporate giveaways?"),
        (695, "out", "Yes! 50pcs up gets tiered pricing. Want the deck?"),
        (690, "in", "Yes please send."),
    ]),
    ("x", "@manilapreloved", "mpl_preloved", 2, [
        (200, "in", "hi! is this the official account? dm'd another page kasi scam pala"),
        (198, "out", "This is our only account. Never transact elsewhere ⚠️"),
        (45,  "in", "noted! so about my order #2231..."),
        (44,  "in", "hindi ko pa siya narereceive"),
    ]),
    ("messenger", "Grace Lim", "grace_lim", 0, [
        (900, "in", "Thank you! Ang ganda nung packaging 😍"),
    ]),
    ("whatsapp", "Marco Villanueva", "marco_v", 0, [
        (1200, "in", "Scheduled delivery po ba every Saturday lang?"),
        (1195, "out", "For NCR po yes, Sat-Tue window. Province MWF."),
    ]),
]


def seed_store() -> None:
    now = time.time()
    for platform, name, ext_key, unread, msgs in SEED:
        cid = f"conv_{ext_key}"
        conv_msgs = []
        for offset_min, direction, text in msgs:
            conv_msgs.append(cx.normalize_message(
                platform=platform, conversation_id=cid,
                sender_name=name if direction == "in" else "You",
                text=text, direction=direction, ts=now - offset_min * 60,
            ))
        last = conv_msgs[-1]
        STORE["conversations"][cid] = {
            "id": cid,
            "platform": platform,
            "title": name,
            "external_ref": ext_key,
            "unread_count": unread if any(m["direction"] == "in" for m in conv_msgs[-3:]) else (unread or 0),
            "last_message": last["text"],
            "updated_at": last["timestamp"],
        }
        STORE["messages"][cid] = conv_msgs


seed_store()


def resolve_conv(platform: str, ext_id: str, display_name: str) -> str:
    """Find-or-create conversation from an external platform identity."""
    cid = f"conv_{cx.slugify(ext_id)}"
    conv = STORE["conversations"].get(cid)
    if conv is None:
        conv = {
            "id": cid, "platform": platform, "title": display_name,
            "external_ref": ext_id, "unread_count": 1,
            "last_message": "", "updated_at": time.time(),
        }
        STORE["conversations"][cid] = conv
        STORE["messages"][cid] = []
    return cid


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class SendBody(BaseModel):
    text: str


class WebhookBody(BaseModel):
    payload: Dict[str, Any]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "service": "message-funnel", "time": time.time(),
            "platforms": sorted(cx.PLATFORMS)}


@app.get("/api/accounts")
def accounts() -> List[Dict[str, Any]]:
    return [
        {"platform": pid, "display_name": meta["name"],
         "handle": f"@{pid}_business", "connected": True, "color": meta["color"]}
        for pid, meta in cx.PLATFORMS.items()
    ]


@app.get("/api/conversations")
def conversations(
    platform: Optional[str] = Query(None),
    unread_only: bool = Query(False),
) -> List[Dict[str, Any]]:
    convs = sorted(STORE["conversations"].values(), key=lambda c: -c["updated_at"])
    if platform:
        if platform not in cx.PLATFORMS:
            raise HTTPException(404, f"unknown platform '{platform}'")
        convs = [c for c in convs if c["platform"] == platform]
    if unread_only:
        convs = [c for c in convs if c["unread_count"] > 0]
    for c in convs:
        c["meta"] = cx.PLATFORMS[c["platform"]]
    return convs


@app.get("/api/conversations/{cid}/messages")
def messages(cid: str) -> List[Dict[str, Any]]:
    if cid not in STORE["conversations"]:
        raise HTTPException(404, f"unknown conversation '{cid}'")
    return STORE["messages"].get(cid, [])


@app.post("/api/conversations/{cid}/read")
def mark_read(cid: str) -> Dict[str, Any]:
    conv = STORE["conversations"].get(cid)
    if not conv:
        raise HTTPException(404, f"unknown conversation '{cid}'")
    conv["unread_count"] = 0
    return {"ok": True, "id": cid, "unread_count": 0}


@app.post("/api/conversations/{cid}/messages")
def send(cid: str, body: SendBody) -> Dict[str, Any]:
    if cid not in STORE["conversations"]:
        raise HTTPException(404, f"unknown conversation '{cid}'")
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "empty message")
    connector = cx.CONNECTORS[STORE["conversations"][cid]["platform"]]
    msg = connector.send_message(STORE, cid, text[:4000])
    return msg


@app.get("/api/webhooks/{platform}")
async def webhook_verify(platform: str, request: "Request"):
    """Meta webhook verification handshake (echoes hub.challenge)."""
    _ = platform
    challenge = request.query_params.get("hub.challenge", "")
    return int(challenge) if challenge.isdigit() else challenge


@app.post("/api/webhooks/{platform}")
def webhook_receive(platform: str, body: WebhookBody) -> Dict[str, Any]:
    if platform == "messenger" or platform == "instagram":
        msgs = cx.normalize_meta_webhook(body.payload, resolve_conv)
    elif platform == "tiktok":
        msgs = cx.normalize_tiktok_webhook(body.payload, resolve_conv)
    elif platform in cx.CONNECTORS:
        msgs = cx.CONNECTORS[platform].parse_webhook(body.payload, resolve_conv)
    else:
        raise HTTPException(404, f"unknown platform '{platform}'")
    for m in msgs:
        conv = STORE["conversations"][m["conversation_id"]]
        conv["last_message"] = m["text"]
        conv["updated_at"] = m["timestamp"]
        conv["unread_count"] += 1
        STORE["messages"].setdefault(m["conversation_id"], []).append(m)
    return {"received": len(msgs)}
