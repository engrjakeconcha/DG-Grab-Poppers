"""Webhook bridge for Daddy Grab Super App mounted into an existing Flask app."""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from flask import jsonify, request
from telegram import Update

from .bot import build_application
from .config import BOT_USERNAME, LOCK_DIR, STATE_DIR, TELEGRAM_BOT_TOKEN

logger = logging.getLogger("daddygrab-webhook")

WEBHOOK_LOCK_FILE = LOCK_DIR / "daddygrab-webhook.lock"
CART_DB_PATH = STATE_DIR / "daddygrab-cart-sessions.sqlite3"


def _cart_api_token() -> str:
    return os.getenv("DADDYGRAB_CART_SESSION_API_TOKEN", "").strip()


def _ensure_cart_db() -> None:
    CART_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(CART_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cart_sessions (
                session_key TEXT PRIMARY KEY,
                items_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            )
            """
        )
        conn.commit()


def _cart_auth_failed() -> bool:
    expected = _cart_api_token()
    if not expected:
        return False
    header = request.headers.get("Authorization", "")
    provided = header.replace("Bearer ", "", 1).strip() if header.startswith("Bearer ") else ""
    return provided != expected


def _purge_expired_sessions() -> None:
    now_ts = int(asyncio.get_event_loop_policy().get_event_loop().time()) if False else int(__import__("time").time())
    with sqlite3.connect(CART_DB_PATH) as conn:
        conn.execute("DELETE FROM cart_sessions WHERE expires_at <= ?", (now_ts,))
        conn.commit()


def _upsert_cart_session(session_key: str, items_json: str, ttl_seconds: int) -> None:
    _ensure_cart_db()
    _purge_expired_sessions()
    import time

    now_iso = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    expires_at = int(time.time()) + max(ttl_seconds, 60)
    with sqlite3.connect(CART_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO cart_sessions (session_key, items_json, updated_at, expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_key) DO UPDATE SET
                items_json = excluded.items_json,
                updated_at = excluded.updated_at,
                expires_at = excluded.expires_at
            """,
            (session_key, items_json, now_iso, expires_at),
        )
        conn.commit()


def _get_cart_session(session_key: str):
    _ensure_cart_db()
    _purge_expired_sessions()
    with sqlite3.connect(CART_DB_PATH) as conn:
        row = conn.execute(
            "SELECT items_json, updated_at, expires_at FROM cart_sessions WHERE session_key = ?",
            (session_key,),
        ).fetchone()
    return row


def webhook_secret() -> str:
    digest = hashlib.sha256(f"{BOT_USERNAME}:{TELEGRAM_BOT_TOKEN}".encode("utf-8")).hexdigest()
    return digest[:32]


def webhook_path() -> str:
    return f"/daddygrab/webhook/{webhook_secret()}"


def webhook_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}{webhook_path()}"


@contextmanager
def _process_lock():
    """Serialize webhook update handling across multiple web workers."""
    WEBHOOK_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(WEBHOOK_LOCK_FILE, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


async def _process_update_payload(data: dict) -> None:
    """Build a fresh PTB application for this request and process one update."""
    app = build_application()
    await app.initialize()
    await app.start()
    try:
        update = Update.de_json(data, app.bot)
        if update:
            await app.process_update(update)
    finally:
        await app.stop()
        await app.shutdown()


def register_webhook_routes(app) -> None:
    @app.post(webhook_path())
    def daddygrab_telegram_webhook():
        data = request.get_json(silent=True) or {}
        try:
            if "update_id" not in data:
                return jsonify({"ok": True, "ignored": True})
            with _process_lock():
                asyncio.run(_process_update_payload(data))
        except Exception as err:
            logger.exception("Daddy Grab webhook update failure: %s", err)
            return jsonify({"ok": True, "ignored": True})
        return jsonify({"ok": True})

    @app.get("/daddygrab/health")
    def daddygrab_health():
        return jsonify({"ok": True, "webhook_path": webhook_path()})

    @app.post("/api/daddygrab/cart-session")
    def daddygrab_cart_session_upsert():
        if _cart_auth_failed():
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        body = request.get_json(silent=True) or {}
        session_key = str(body.get("session_key") or "").strip()
        items = body.get("items") or []
        ttl_seconds = int(body.get("ttl_seconds") or 1800)
        if not session_key:
            return jsonify({"ok": False, "error": "Missing session_key"}), 400
        if not isinstance(items, list):
            return jsonify({"ok": False, "error": "items must be a list"}), 400
        _upsert_cart_session(session_key, __import__("json").dumps(items), ttl_seconds)
        return jsonify({"ok": True, "data": {"session_key": session_key, "items": items}})

    @app.get("/api/daddygrab/cart-session/<path:session_key>")
    def daddygrab_cart_session_get(session_key: str):
        if _cart_auth_failed():
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        row = _get_cart_session(session_key)
        if not row:
            return jsonify({"ok": False, "error": "Not found"}), 404
        items_json, updated_at, expires_at = row
        try:
            items = __import__("json").loads(items_json or "[]")
        except Exception:
            items = []
        return jsonify(
            {
                "ok": True,
                "data": {
                    "session_key": session_key,
                    "items": items if isinstance(items, list) else [],
                    "updated_at": updated_at,
                    "expires_at": expires_at,
                },
            }
        )
