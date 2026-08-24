"""MessageFunnel — platform catalog + connection validation.

Each platform declares the credential fields a user must supply in Settings.
`validate_connection` performs structural checks now; live API probes are the
v2 step once real developer apps exist (see connectors.py notes).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

PLATFORM_CATALOG: Dict[str, Dict[str, Any]] = {
    "messenger": {
        "name": "Messenger",
        "color": "#0084FF",
        "docs": "https://developers.facebook.com/docs/messenger-platform",
        "fields": [
            {"key": "page_id",          "label": "Page ID",           "type": "text",     "required": True,  "secret": False},
            {"key": "page_access_token","label": "Page Access Token", "type": "password", "required": True,  "secret": True},
            {"key": "app_secret",       "label": "App Secret",        "type": "password", "required": False, "secret": True},
            {"key": "verify_token",     "label": "Webhook Verify Token", "type": "password", "required": False, "secret": True},
        ],
    },
    "instagram": {
        "name": "Instagram DMs",
        "color": "#E1306C",
        "docs": "https://developers.facebook.com/docs/messenger-platform/instagram",
        "fields": [
            {"key": "ig_user_id",       "label": "IG Professional Account ID", "type": "text", "required": True, "secret": False},
            {"key": "page_access_token","label": "Page Access Token",  "type": "password", "required": True,  "secret": True},
            {"key": "app_secret",       "label": "App Secret",         "type": "password", "required": False, "secret": True},
        ],
    },
    "tiktok": {
        "name": "TikTok",
        "color": "#FE2C55",
        "docs": "https://developers.tiktok.com/doc/business-api-overview",
        "fields": [
            {"key": "access_token",     "label": "Business Access Token", "type": "password", "required": True, "secret": True},
            {"key": "app_key",          "label": "App Key",            "type": "text",     "required": True,  "secret": False},
            {"key": "app_secret",       "label": "App Secret",         "type": "password", "required": True,  "secret": True},
        ],
    },
    "whatsapp": {
        "name": "WhatsApp Cloud",
        "color": "#25D366",
        "docs": "https://developers.facebook.com/docs/whatsapp/cloud-api",
        "fields": [
            {"key": "phone_number_id",  "label": "Phone Number ID",    "type": "text",     "required": True,  "secret": False},
            {"key": "access_token",     "label": "Access Token",       "type": "password", "required": True,  "secret": True},
        ],
    },
    "telegram": {
        "name": "Telegram Bot",
        "color": "#229ED9",
        "docs": "https://core.telegram.org/bots/api",
        "fields": [
            {"key": "bot_token",        "label": "Bot Token",          "type": "password", "required": True,  "secret": True},
            {"key": "bot_username",     "label": "Bot Username",       "type": "text",     "required": False, "secret": False},
        ],
    },
    "x": {
        "name": "X / DMs",
        "color": "#8899A6",
        "docs": "https://developer.x.com/en/docs/twitter-api/v1/dms/introduction",
        "fields": [
            {"key": "api_key",          "label": "API Key",            "type": "text",     "required": True,  "secret": False},
            {"key": "api_key_secret",   "label": "API Key Secret",     "type": "password", "required": True,  "secret": True},
            {"key": "access_token",     "label": "Access Token",       "type": "text",     "required": True,  "secret": False},
            {"key": "access_token_secret", "label": "Access Token Secret", "type": "password", "required": True, "secret": True},
        ],
    },
}


def validate_credentials(platform: str, creds: Dict[str, str]) -> Tuple[bool, str]:
    """Structural validation. Returns (ok, error_message)."""
    spec = PLATFORM_CATALOG.get(platform)
    if not spec:
        return False, f"unknown platform '{platform}'"
    for field in spec["fields"]:
        val = (creds.get(field["key"]) or "").strip()
        if field["required"] and not val:
            return False, f"missing required field: {field['label']}"
        if val and len(val) > 4096:
            return False, f"field too long: {field['label']}"
    # light format heuristics
    if platform == "telegram":
        tok = (creds.get("bot_token") or "").strip()
        if tok and ":" not in tok:
            return False, "Telegram bot tokens look like '123456:ABC-DEF...'"
    if platform == "messenger" or platform == "instagram":
        tok = (creds.get("page_access_token") or "").strip()
        if tok and len(tok) < 20:
            return False, "Page access token looks too short"
    extra = set(creds) - {f["key"] for f in spec["fields"]}
    if extra:
        return False, f"unknown fields for {platform}: {', '.join(sorted(extra))}"
    return True, ""


def masked_creds(platform: str, creds: Dict[str, str]) -> List[Dict[str, Any]]:
    """Per-field view for the settings UI — secrets masked, names kept."""
    from .security import mask_value
    out: List[Dict[str, Any]] = []
    for field in PLATFORM_CATALOG.get(platform, {}).get("fields", []):
        val = creds.get(field["key"], "")
        out.append({
            "key": field["key"],
            "label": field["label"],
            "required": field["required"],
            "is_secret": field["secret"],
            "set": bool((val or "").strip()),
            "masked_value": mask_value(val) if field["secret"] else val,
        })
    return out
