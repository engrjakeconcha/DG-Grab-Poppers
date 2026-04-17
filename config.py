"""Configuration for the Daddy Grab Super App Telegram bot."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _parse_admin_ids(value: str) -> list[int]:
    ids: list[int] = []
    for chunk in value.split(","):
        raw = chunk.strip()
        if raw.lstrip("-").isdigit():
            ids.append(int(raw))
    return ids


def _parse_service_account(value: str):
    if not value.strip():
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


# Telegram
TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "",
).strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "DGrabstgbot").strip().lstrip("@")

# Admins
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "8488339614"))
ADMIN_IDS = _parse_admin_ids(os.getenv("ADMIN_IDS", "8488339614")) or [ADMIN_USER_ID]
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "-1003785747521"))

# Store settings
STORE_NAME = os.getenv("STORE_NAME", "Daddy Grab Super App").strip()
GSHEET_NAME = os.getenv("GSHEET_NAME", "Daddy Grab Super App Sales - Staging").strip()
GSHEET_ID = os.getenv("GSHEET_ID", "").strip()
SHIPPING_PROVINCIAL = int(os.getenv("SHIPPING_PROVINCIAL", "100"))
WHOLESALE_THRESHOLD = int(os.getenv("WHOLESALE_THRESHOLD", "30"))
COD_FEE = int(os.getenv("COD_FEE", "50"))

# Hosted app URLs
MINIAPP_URL = os.getenv("MINIAPP_URL", "http://daddygrab.online/").strip()
REPORT_ISSUE_URL = os.getenv("REPORT_ISSUE_URL", "https://daddygrab.online/report").strip()
ADMIN_URL = os.getenv("ADMIN_URL", "http://daddygrab.online/admin").strip()

# Runtime paths
RUNTIME_ROOT = Path(os.getenv("DADDYGRAB_RUNTIME_ROOT", "/opt/daddygrab-super-app")).expanduser()
STATE_DIR = RUNTIME_ROOT / "state"
LOCK_DIR = RUNTIME_ROOT / "locks"

# Google Service Account (service_account.json contents)
SERVICE_ACCOUNT_INFO = _parse_service_account(os.getenv("SERVICE_ACCOUNT_INFO_JSON", "")) or {}

START_IMAGE_PATH = os.getenv("START_IMAGE_PATH", "Assets/hero.jpg").strip()
ORDER_COMPLETE_IMAGE_PATH = os.getenv("ORDER_COMPLETE_IMAGE_PATH", "Assets/thankyou.png").strip()
