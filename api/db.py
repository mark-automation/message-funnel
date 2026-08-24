"""SQLite persistence layer — users, platform connections, conversations, messages.

WAL mode, check_same_thread=False guarded by a lock (low-traffic service).
Credentials are stored encrypted (Fernet) — see security.py.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import security

_DB_PATH = Path(os.environ.get(
    "MF_DATA_DIR",
    Path(__file__).resolve().parent.parent / "data",
)) / "messagefunnel.db"
_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _DB_PATH.parent.mkdir(exist_ok=True)
        _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        init_schema(_conn)
    return _conn


def init_schema(c: sqlite3.Connection) -> None:
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS connections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        platform TEXT NOT NULL,
        handle TEXT NOT NULL DEFAULT '',
        credentials_enc TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'connected',
        connected_at REAL NOT NULL,
        UNIQUE(user_id, platform)
    );
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        connection_id INTEGER NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
        platform TEXT NOT NULL,
        external_ref TEXT NOT NULL,
        title TEXT NOT NULL,
        unread_count INTEGER NOT NULL DEFAULT 0,
        last_message TEXT NOT NULL DEFAULT '',
        updated_at REAL NOT NULL,
        UNIQUE(connection_id, external_ref)
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        platform TEXT NOT NULL,
        sender_name TEXT NOT NULL,
        text TEXT NOT NULL,
        direction TEXT NOT NULL CHECK(direction IN ('in','out')),
        timestamp REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, updated_at DESC);
    CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, timestamp);
    """)
    c.commit()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def create_user(email: str, password: str, display_name: str) -> Optional[Dict[str, Any]]:
    with _lock:
        cur = get_conn().execute(
            "INSERT INTO users(email,password_hash,display_name,created_at) VALUES(?,?,?,?)",
            (email.strip().lower(), security.hash_password(password), display_name, time.time()),
        )
        get_conn().commit()
        return get_user_by_id(cur.lastrowid)


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    row = get_conn().execute(
        "SELECT * FROM users WHERE email=?", (email.strip().lower(),)
    ).fetchone()
    return dict(row) if row else None


def get_user_by_id(uid: int) -> Optional[Dict[str, Any]]:
    row = get_conn().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Connections (one place for all platform credentials)
# ---------------------------------------------------------------------------
def upsert_connection(user_id: int, platform: str, handle: str,
                      creds: Dict[str, Any]) -> Dict[str, Any]:
    enc = security.encrypt_credentials(creds)
    now = time.time()
    with _lock:
        c = get_conn()
        existing = c.execute(
            "SELECT id FROM connections WHERE user_id=? AND platform=?",
            (user_id, platform),
        ).fetchone()
        if existing:
            c.execute(
                """UPDATE connections SET handle=?, credentials_enc=?, status='connected',
                   connected_at=? WHERE id=?""",
                (handle, enc, now, existing["id"]),
            )
            cid_ = existing["id"]
        else:
            cur = c.execute(
                """INSERT INTO connections(user_id,platform,handle,credentials_enc,status,connected_at)
                   VALUES(?,?,?,?,'connected',?)""",
                (user_id, platform, handle, enc, now),
            )
            cid_ = cur.lastrowid
        c.commit()
    return get_connection(user_id, cid_)  # type: ignore[return-value]


def list_connections(user_id: int) -> List[Dict[str, Any]]:
    rows = get_conn().execute(
        "SELECT * FROM connections WHERE user_id=? ORDER BY platform", (user_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_connection(user_id: int, conn_id: int) -> Optional[Dict[str, Any]]:
    row = get_conn().execute(
        "SELECT * FROM connections WHERE id=? AND user_id=?", (conn_id, user_id)
    ).fetchone()
    return dict(row) if row else None


def get_connection_by_platform(user_id: int, platform: str) -> Optional[Dict[str, Any]]:
    row = get_conn().execute(
        "SELECT * FROM connections WHERE user_id=? AND platform=?", (user_id, platform)
    ).fetchone()
    return dict(row) if row else None


def delete_connection(user_id: int, conn_id: int) -> bool:
    with _lock:
        c = get_conn()
        cur = c.execute("DELETE FROM connections WHERE id=? AND user_id=?", (conn_id, user_id))
        c.commit()
        return cur.rowcount > 0


def public_connection(row: Dict[str, Any]) -> Dict[str, Any]:
    """Strip the encrypted blob; show masked credential keys instead."""
    creds = security.decrypt_credentials(row.get("credentials_enc", ""))
    return {
        "id": row["id"],
        "platform": row["platform"],
        "handle": row["handle"],
        "status": row["status"],
        "connected_at": row["connected_at"],
        "credential_fields": [k for k in creds.keys()],
        "masked": {k: security.mask_value(v) for k, v in creds.items() if isinstance(v, str)},
    }


# ---------------------------------------------------------------------------
# Conversations + messages
# ---------------------------------------------------------------------------
def resolve_conversation(conn_id: int, user_id: int, platform: str,
                         ext_ref: str, title: str) -> int:
    with _lock:
        c = get_conn()
        row = c.execute(
            "SELECT id FROM conversations WHERE connection_id=? AND external_ref=?",
            (conn_id, ext_ref),
        ).fetchone()
        if row:
            return int(row["id"])
        cur = c.execute(
            """INSERT INTO conversations(user_id,connection_id,platform,external_ref,title,
               unread_count,last_message,updated_at) VALUES(?,?,?,?,?,0,'',?)""",
            (user_id, conn_id, platform, ext_ref, title, time.time()),
        )
        c.commit()
        return int(cur.lastrowid)


def append_message(conversation_id: int, platform: str, sender_name: str,
                   text: str, direction: str, ts: Optional[float] = None) -> Dict[str, Any]:
    ts = ts or time.time()
    with _lock:
        c = get_conn()
        cur = c.execute(
            """INSERT INTO messages(conversation_id,platform,sender_name,text,direction,timestamp)
               VALUES(?,?,?,?,?,?)""",
            (conversation_id, platform, sender_name, text, direction, ts),
        )
        bump_unread = ", unread_count = unread_count + 1" if direction == "in" else ""
        c.execute(
            f"""UPDATE conversations SET last_message=?, updated_at=?{bump_unread}
                WHERE id=?""",
            (text, ts, conversation_id),
        )
        c.commit()
        row = c.execute("SELECT * FROM messages WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)


def list_conversations(user_id: int, platform: Optional[str] = None,
                       unread_only: bool = False) -> List[Dict[str, Any]]:
    q = "SELECT * FROM conversations WHERE user_id=?"
    params: List[Any] = [user_id]
    if platform:
        q += " AND platform=?"
        params.append(platform)
    if unread_only:
        q += " AND unread_count>0"
    q += " ORDER BY updated_at DESC"
    rows = get_conn().execute(q, params).fetchall()
    return [dict(r) for r in rows]


def get_conversation(user_id: int, conv_id: int) -> Optional[Dict[str, Any]]:
    row = get_conn().execute(
        "SELECT * FROM conversations WHERE id=? AND user_id=?", (conv_id, user_id)
    ).fetchone()
    return dict(row) if row else None


def list_messages(conv_id: int) -> List[Dict[str, Any]]:
    rows = get_conn().execute(
        "SELECT * FROM messages WHERE conversation_id=? ORDER BY timestamp,id", (conv_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def mark_read(user_id: int, conv_id: int) -> bool:
    with _lock:
        c = get_conn()
        cur = c.execute(
            "UPDATE conversations SET unread_count=0 WHERE id=? AND user_id=?",
            (conv_id, user_id),
        )
        c.commit()
        return cur.rowcount > 0


def counts(user_id: int) -> Tuple[int, int]:
    r = get_conn().execute(
        "SELECT COUNT(*) AS c, COALESCE(SUM(unread_count),0) AS u "
        "FROM conversations WHERE user_id=?",
        (user_id,),
    ).fetchone()
    return int(r["c"]), int(r["u"])
