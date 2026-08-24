"""Security primitives: password hashing, JWT, credential encryption.

All stdlib except Fernet (cryptography) for encrypting platform credentials
at rest. Secrets never leave the server unmasked.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

# ---------------------------------------------------------------------------
# Master secret (JWT signing + credential encryption key derivation)
# ---------------------------------------------------------------------------
def _data_dir() -> Path:
    d = Path(os.environ.get(
        "MF_DATA_DIR",
        Path(__file__).resolve().parent.parent / "data",
    ))
    d.mkdir(parents=True, exist_ok=True)
    return d


def master_secret() -> bytes:
    env = os.environ.get("MF_SECRET")
    if env:
        return env.encode()
    keyfile = _data_dir() / "secret.key"
    if not keyfile.exists():
        keyfile.write_bytes(secrets.token_urlsafe(48).encode())
    return keyfile.read_bytes()


_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        digest = hashlib.sha256(master_secret()).digest()
        _fernet = Fernet(base64.urlsafe_b64encode(digest))
    return _fernet


# ---------------------------------------------------------------------------
# Passwords — PBKDF2-HMAC-SHA256 (stdlib, no native deps)
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, dk_hex = stored.split("$", 1)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    return hmac.compare_digest(dk.hex(), dk_hex)


# ---------------------------------------------------------------------------
# JWT — minimal HS256 implementation (no extra dependency)
# ---------------------------------------------------------------------------
TOKEN_TTL_SECONDS = 7 * 24 * 3600


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def create_token(user_id: int) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({
        "sub": str(user_id),
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }).encode())
    signing_input = f"{header}.{payload}".encode()
    sig = hmac.new(master_secret(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(sig)}"


def decode_token(token: str) -> Optional[int]:
    """Return user_id or None if invalid/expired."""
    try:
        header, payload, sig = token.split(".")
        signing_input = f"{header}.{payload}".encode()
        expected = hmac.new(master_secret(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig)):
            return None
        claims = json.loads(_b64url_decode(payload))
        if claims.get("exp", 0) < time.time():
            return None
        return int(claims["sub"])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Platform credential encryption at rest
# ---------------------------------------------------------------------------
def encrypt_credentials(creds: Dict[str, Any]) -> str:
    return _get_fernet().encrypt(json.dumps(creds).encode()).decode()


def decrypt_credentials(blob: str) -> Dict[str, Any]:
    try:
        return json.loads(_get_fernet().decrypt(blob.encode()))
    except (InvalidToken, Exception):
        return {}


def mask_value(value: str) -> str:
    if len(value) <= 4:
        return "••••"
    return "••••" + value[-4:]
