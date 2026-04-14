"""Daddy Grab Super App Telegram bot."""

import asyncio
import csv
import datetime as dt
import html
import io
import json
import logging
import os
import re
import shutil
import threading
import textwrap
import time
import uuid
from urllib import parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from google.oauth2.service_account import Credentials
import gspread

from telegram import (
    BotCommand,
    BotCommandScopeChatMember,
    BotCommandScopeDefault,
    InputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
    WebAppInfo,
)
from telegram.error import BadRequest
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    BasePersistence,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ConversationHandler,
    DictPersistence,
    MessageHandler,
    PersistenceInput,
    filters,
    ContextTypes,
)

try:
    from .config import (
        TELEGRAM_BOT_TOKEN,
        BOT_USERNAME,
        ADMIN_IDS,
        ADMIN_GROUP_ID,
        STORE_NAME,
        GSHEET_NAME,
        GSHEET_ID,
        SHIPPING_PROVINCIAL,
        COD_FEE,
        WHOLESALE_THRESHOLD,
        SERVICE_ACCOUNT_INFO,
        START_IMAGE_PATH,
        ORDER_COMPLETE_IMAGE_PATH,
        MINIAPP_URL,
        ADMIN_URL,
        STATE_DIR,
        LOCK_DIR,
    )
except ImportError:
    from config import (
        TELEGRAM_BOT_TOKEN,
        BOT_USERNAME,
        ADMIN_IDS,
        ADMIN_GROUP_ID,
        STORE_NAME,
        GSHEET_NAME,
        GSHEET_ID,
        SHIPPING_PROVINCIAL,
        COD_FEE,
        WHOLESALE_THRESHOLD,
        SERVICE_ACCOUNT_INFO,
        START_IMAGE_PATH,
        ORDER_COMPLETE_IMAGE_PATH,
        MINIAPP_URL,
        ADMIN_URL,
        STATE_DIR,
        LOCK_DIR,
    )

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("daddygrab-bot")

INSTANCE_LOCK_ROOT = LOCK_DIR
INSTANCE_LOCK_STALE_SECONDS = 120
PERSISTENCE_PATH = STATE_DIR / "daddygrab-bot.json"
DADDY_GRAB_MINIAPP_URL = MINIAPP_URL
DADDY_GRAB_ADMIN_URL = ADMIN_URL


class JsonFilePersistence(BasePersistence):
    """Minimal JSON-backed persistence for user_data + conversations only."""

    def __init__(self, filepath: str) -> None:
        super().__init__(
            store_data=PersistenceInput(
                user_data=True,
                chat_data=False,
                bot_data=False,
                callback_data=False,
            )
        )
        self.filepath = Path(filepath)
        self._delegate = DictPersistence(
            store_data=PersistenceInput(
                user_data=True,
                chat_data=False,
                bot_data=False,
                callback_data=False,
            )
        )
        self._loaded = False

    def _serialize(self, value):
        if isinstance(value, Product):
            return {
                "__type__": "Product",
                "sku": value.sku,
                "category": value.category,
                "name": value.name,
                "description": value.description,
                "price": value.price,
                "image_url": value.image_url,
                "active": value.active,
                "stock": value.stock,
            }
        if isinstance(value, dict):
            return {str(key): self._serialize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._serialize(item) for item in value]
        if isinstance(value, tuple):
            return [self._serialize(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def _deserialize(self, value):
        if isinstance(value, dict):
            if value.get("__type__") == "Product":
                return Product(
                    sku=str(value.get("sku", "")),
                    category=str(value.get("category", "")),
                    name=str(value.get("name", "")),
                    description=str(value.get("description", "")),
                    price=float(value.get("price", 0) or 0),
                    image_url=str(value.get("image_url", "")),
                    active=bool(value.get("active", False)),
                    stock=int(value.get("stock", 0) or 0),
                )
            return {key: self._deserialize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._deserialize(item) for item in value]
        return value

    def _load(self) -> None:
        if self._loaded:
            return
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        if self.filepath.exists():
            try:
                raw = json.loads(self.filepath.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to load persistence file %s: %s", self.filepath, exc)
                raw = {}
        else:
            raw = {}
        self._delegate = DictPersistence(
            store_data=PersistenceInput(
                user_data=True,
                chat_data=False,
                bot_data=False,
                callback_data=False,
            ),
            user_data_json=json.dumps(raw.get("user_data", {})),
            conversations_json=json.dumps(raw.get("conversations", {})),
        )
        self._loaded = True

    async def get_user_data(self):
        self._load()
        raw = await self._delegate.get_user_data()
        return self._deserialize(raw)

    async def get_chat_data(self):
        return {}

    async def get_bot_data(self):
        return {}

    async def get_callback_data(self):
        return None

    async def get_conversations(self, name: str):
        self._load()
        return await self._delegate.get_conversations(name)

    async def update_conversation(self, name: str, key, new_state) -> None:
        self._load()
        await self._delegate.update_conversation(name, key, new_state)

    async def update_user_data(self, user_id: int, data) -> None:
        self._load()
        await self._delegate.update_user_data(user_id, data)

    async def update_chat_data(self, chat_id: int, data) -> None:
        return None

    async def update_bot_data(self, data) -> None:
        return None

    async def update_callback_data(self, data) -> None:
        return None

    async def drop_chat_data(self, chat_id: int) -> None:
        return None

    async def drop_user_data(self, user_id: int) -> None:
        self._load()
        await self._delegate.drop_user_data(user_id)

    async def refresh_user_data(self, user_id: int, user_data) -> None:
        return None

    async def refresh_chat_data(self, chat_id: int, chat_data) -> None:
        return None

    async def refresh_bot_data(self, bot_data) -> None:
        return None

    async def flush(self) -> None:
        self._load()
        payload = {
            "user_data": self._serialize(await self._delegate.get_user_data()),
            "conversations": json.loads(self._delegate.conversations_json or "{}"),
        }
        self.filepath.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


class InstanceLock:
    def __init__(self, name: str) -> None:
        self.name = name
        self.lock_dir = INSTANCE_LOCK_ROOT / name
        self.owner_file = self.lock_dir / "owner.txt"
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    def __enter__(self) -> "InstanceLock":
        INSTANCE_LOCK_ROOT.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                self.lock_dir.mkdir()
                self.owner_file.write_text(f"{os.getpid()}\n{time.time()}\n", encoding="utf-8")
                self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
                self._heartbeat_thread.start()
                return self
            except FileExistsError:
                if self._is_stale():
                    self._break_stale_lock()
                    continue
                raise RuntimeError(f"{self.name} instance lock is already held")

    def __exit__(self, exc_type, exc, tb) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=1)
        self._break_stale_lock()

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(15):
            try:
                self.owner_file.write_text(f"{os.getpid()}\n{time.time()}\n", encoding="utf-8")
            except OSError:
                logger.exception("Failed to refresh instance lock heartbeat for %s", self.name)

    def _is_stale(self) -> bool:
        try:
            return time.time() - self.owner_file.stat().st_mtime > INSTANCE_LOCK_STALE_SECONDS
        except FileNotFoundError:
            return False

    def _break_stale_lock(self) -> None:
        shutil.rmtree(self.lock_dir, ignore_errors=True)

# Reduce Sheets API load from very active groups.
MEMBER_CAPTURE_THROTTLE_SECONDS = 300

PUBLIC_COMMANDS = [
    BotCommand("start", "Start bot"),
    BotCommand("help", "Show help"),
    BotCommand("cancel", "Cancel current flow"),
    BotCommand("rewards", "Loyalty points and referral link"),
    BotCommand("received", "Confirm order received"),
]

ADMIN_COMMANDS = [
    BotCommand("admin", "Open admin console"),
    BotCommand("setup", "Setup/repair sheets"),
    BotCommand("status", "Bot status"),
    BotCommand("pending_orders", "Show pending orders"),
    BotCommand("send_tracking", "Guided tracking sender"),
    BotCommand("send_tracking_link", "Send tracking link by order ID"),
    BotCommand("payment_queue", "Payment verification queue"),
    BotCommand("sales_dashboard", "Sales KPI snapshot"),
    BotCommand("broadcast", "Broadcast to users"),
    BotCommand("broadcast_groups", "Broadcast to groups"),
    BotCommand("broadcast_channels", "Broadcast to channels"),
    BotCommand("broadcast_group_members", "Broadcast to captured group members"),
    BotCommand("export_users", "Export users CSV"),
    BotCommand("export_groups", "Export groups CSV"),
    BotCommand("export_channels", "Export channels CSV"),
    BotCommand("export_group_members", "Export group members CSV"),
    BotCommand("update_status", "Update order status"),
    BotCommand("reply", "Reply to user"),
    BotCommand("rollback", "Rollback latest order status"),
]

ORDER_HEADERS = [
    "order_id",
    "created_at",
    "user_id",
    "username",
    "full_name",
    "items_json",
    "subtotal",
    "discount",
    "shipping",
    "total",
    "delivery_name",
    "delivery_address",
    "delivery_contact",
    "delivery_area",
    "payment_method",
    "payment_proof_file_id",
    "status",
    "tracking_number",
]
MESSAGE_HEADERS = [
    "message_id",
    "created_at",
    "order_id",
    "ticket_id",
    "user_id",
    "username",
    "sender_type",
    "sender_name",
    "message",
    "telegram_message_id",
    "reply_to_message_id",
    "read_by_admin",
]

ABANDONED_CART_REMINDER_MINUTES = 45
LOYALTY_POINTS_PER_ORDER = 10
LOYALTY_REDEEM_POINTS = 1000
LOYALTY_REDEEM_VALUE = 100
REFERRAL_SUCCESS_POINTS = 50
COD_RISK_CANCEL_THRESHOLD = 3
PROMO_TERMS_TEXT = (
    "Rewards Terms\n"
    f"• Every completed order earns {LOYALTY_POINTS_PER_ORDER} points.\n"
    f"• One successful referral earns {REFERRAL_SUCCESS_POINTS} points after the referred customer completes their first successful order.\n"
    f"• {LOYALTY_REDEEM_POINTS} points automatically redeem for ₱{LOYALTY_REDEEM_VALUE} off at checkout.\n"
    "• Auto-redemption applies before payment once the account has enough points.\n"
    "• If an order is rejected or cancelled after redemption, redeemed points are returned automatically.\n"
    "• Points have no cash value and are non-transferable."
)


# Conversation states
(
    CONSENT,
    MENU,
    ORDERING,
    DELIVERY_AREA,
    DELIVERY_NAME,
    DELIVERY_ADDRESS,
    DELIVERY_CONTACT,
    PROMO_CODE,
    PAYMENT_METHOD,
    PAYMENT_PROOF,
    TRACK_CHOICE,
    TRACK_INPUT,
    CS_FORM,
    BULK_FORM,
    AFFILIATE_TWITTER,
    AFFILIATE_EMAIL,
    AFFILIATE_CONTACT,
    AFFILIATE_SUBS,
    BROADCAST_MESSAGE,
    CUSTOM_QTY,
    TRACKING_SELECT,
    TRACKING_LINK,
    BROADCAST_PREVIEW,
) = range(23)


@dataclass
class Product:
    """Represents a product loaded from Google Sheets."""

    sku: str
    category: str
    name: str
    description: str
    price: float
    image_url: str
    active: bool
    stock: int


@dataclass
class Promo:
    """Represents a promo code."""

    code: str
    discount: float
    active: bool


class SheetsClient:
    """Google Sheets wrapper for reading and writing bot data."""

    def __init__(self) -> None:
        if not TELEGRAM_BOT_TOKEN:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
        if not SERVICE_ACCOUNT_INFO:
            raise RuntimeError("SERVICE_ACCOUNT_INFO_JSON is required")
        creds = Credentials.from_service_account_info(
            SERVICE_ACCOUNT_INFO,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
        self.gc = gspread.authorize(creds)
        if GSHEET_ID:
            self.sheet = self.gc.open_by_key(GSHEET_ID)
        else:
            try:
                self.sheet = self.gc.open(GSHEET_NAME)
            except gspread.SpreadsheetNotFound:
                logger.info("Spreadsheet %s not found. Creating a fresh staging sheet.", GSHEET_NAME)
                self.sheet = self.gc.create(GSHEET_NAME)

    @staticmethod
    def _is_transient_error(exc: Exception) -> bool:
        """Return True for temporary Google Sheets/API failures worth retrying."""
        if isinstance(exc, gspread.exceptions.APIError):
            try:
                code = int(getattr(exc.response, "status_code", 0) or 0)
            except Exception:
                code = 0
            if code in {429, 500, 502, 503, 504}:
                return True
        message = str(exc).lower()
        transient_tokens = [
            "unavailable",
            "timed out",
            "timeout",
            "connection reset",
            "temporarily unavailable",
            "internal error",
            "bad gateway",
        ]
        return any(token in message for token in transient_tokens)

    def _with_retry(self, label: str, func, *args, **kwargs):
        """Retry transient worksheet operations to reduce dropped orders."""
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt == 2 or not self._is_transient_error(exc):
                    raise
                delay = 0.8 * (attempt + 1)
                logger.warning("%s failed (%s). Retrying in %.1fs", label, exc, delay)
                time.sleep(delay)
        if last_exc:
            raise last_exc

    def _get_or_create_ws(self, title: str, headers: List[str]) -> gspread.Worksheet:
        """Get a worksheet by title or create it with headers."""
        try:
            ws = self._with_retry(f"worksheet:{title}", self.sheet.worksheet, title)
        except gspread.WorksheetNotFound:
            ws = self._with_retry(
                f"add_worksheet:{title}",
                self.sheet.add_worksheet,
                title=title,
                rows=2000,
                cols=len(headers),
            )
            self._with_retry(f"append_headers:{title}", ws.append_row, headers)
        return ws

    @staticmethod
    def _normalize_order_id(value: Any) -> str:
        """Normalize order id input for robust matching."""
        raw = str(value or "").strip()
        raw = raw.replace("`", "").replace(" ", "")
        return raw.upper()

    @staticmethod
    def _safe_get_all_records(ws: gspread.Worksheet, headers: List[str]) -> List[Dict[str, Any]]:
        """Get records with expected headers to avoid duplicate-header issues."""
        try:
            sheet_headers = ws.row_values(1)
            if sheet_headers and all(h in sheet_headers for h in headers):
                return ws.get_all_records(expected_headers=headers)
            # Fallback to default behavior if headers don't match
            return ws.get_all_records()
        except Exception as exc:
            logger.warning("get_all_records failed for %s: %s", ws.title, exc)
            data = ws.get_all_values()
            if not data:
                return []
            raw_headers = data[0]
            # Deduplicate headers if needed
            deduped = []
            seen: Dict[str, int] = {}
            for h in raw_headers:
                key = h.strip() or "column"
                count = seen.get(key, 0)
                seen[key] = count + 1
                deduped.append(f"{key}_{count}" if count else key)
            use_headers = headers if len(headers) == len(deduped) else deduped
            records = []
            for row in data[1:]:
                padded = row + [""] * (len(use_headers) - len(row))
                records.append(dict(zip(use_headers, padded)))
            return records

    def get_products(self) -> List[Product]:
        """Load products from the Products worksheet."""
        ws = self._get_or_create_ws(
            "Products", ["sku", "category", "name", "description", "price", "image_url", "active", "stock"]
        )
        try:
            rows = ws.get_all_records()
        except Exception as exc:
            logger.warning("Products get_all_records failed: %s", exc)
            rows = self._safe_get_all_records(
                ws, ["sku", "category", "name", "description", "price", "image_url", "active", "stock"]
            )
        products = []
        for row in rows:
            try:
                row_lower = {str(k).lower(): v for k, v in row.items()}
                sku = str(row.get("sku", "")).strip()
                category = str(
                    row.get("category", row.get("Category", "") or row_lower.get("category", "") or "")
                ).strip() or "Uncategorized"
                name = str(row.get("name", row_lower.get("name", ""))).strip()
                description = str(
                    row.get("description", row.get("Description", "") or row_lower.get("description", "") or "")
                ).strip()
                price = float(row.get("price", row_lower.get("price", 0)) or 0)
                image_url = str(row.get("image_url", row_lower.get("image_url", ""))).strip()
                active = str(row.get("active", row_lower.get("active", ""))).strip().lower() in [
                    "yes",
                    "true",
                    "1",
                    "active",
                ]
                raw_stock = row.get("stock", row_lower.get("stock", ""))
                if str(raw_stock).strip() == "":
                    stock = 999999
                else:
                    stock = int(float(raw_stock))
                if sku and name:
                    products.append(
                        Product(
                            sku=sku,
                            category=category,
                            name=name,
                            description=description,
                            price=price,
                            image_url=image_url,
                            active=active,
                            stock=stock,
                        )
                    )
            except Exception as exc:
                logger.warning("Failed to parse product row: %s", exc)
        return [p for p in products if p.active and p.stock > 0]

    def _products_ws(self) -> gspread.Worksheet:
        return self._get_or_create_ws(
            "Products", ["sku", "category", "name", "description", "price", "image_url", "active", "stock"]
        )

    def reserve_stock(self, items: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """Atomically-ish check and decrement stock in sheet for ordered items."""
        ws = self._products_ws()
        rows = self._safe_get_all_records(
            ws, ["sku", "category", "name", "description", "price", "image_url", "active", "stock"]
        )
        by_sku = {str(r.get("sku", "")).strip(): r for r in rows}
        for item in items:
            sku = str(item.get("sku", "")).strip()
            qty = int(item.get("qty", 0) or 0)
            row = by_sku.get(sku)
            if not row:
                return False, f"SKU {sku} not found."
            current = int(float(row.get("stock", 0) or 0))
            if current < qty:
                return False, f"{sku} has only {current} left."
        # Update only after all checks pass.
        for idx, row in enumerate(rows, start=2):
            sku = str(row.get("sku", "")).strip()
            item = next((i for i in items if str(i.get("sku", "")).strip() == sku), None)
            if not item:
                continue
            qty = int(item.get("qty", 0) or 0)
            current = int(float(row.get("stock", 0) or 0))
            self._with_retry(
                f"reserve_stock:{sku}",
                ws.update,
                range_name=f"H{idx}:H{idx}",
                values=[[max(current - qty, 0)]],
            )
        return True, ""

    def restore_stock(self, items: List[Dict[str, Any]]) -> None:
        """Add reserved stock back if order creation fails after decrementing."""
        ws = self._products_ws()
        rows = self._safe_get_all_records(
            ws, ["sku", "category", "name", "description", "price", "image_url", "active", "stock"]
        )
        for idx, row in enumerate(rows, start=2):
            sku = str(row.get("sku", "")).strip()
            item = next((i for i in items if str(i.get("sku", "")).strip() == sku), None)
            if not item:
                continue
            qty = int(item.get("qty", 0) or 0)
            current = int(float(row.get("stock", 0) or 0))
            self._with_retry(
                f"restore_stock:{sku}",
                ws.update,
                range_name=f"H{idx}:H{idx}",
                values=[[current + qty]],
            )

    def get_promos(self) -> Dict[str, Promo]:
        """Load promo codes from the Promos worksheet."""
        ws = self._get_or_create_ws("Promos", ["code", "discount", "active"])
        rows = self._safe_get_all_records(ws, ["code", "discount", "active"])
        promos = {}
        for row in rows:
            try:
                code = str(row.get("code", "")).strip().upper()
                discount = float(row.get("discount", 0))
                active = str(row.get("active", "")).strip().lower() in [
                    "yes",
                    "true",
                    "1",
                    "active",
                ]
                if code:
                    promos[code] = Promo(code=code, discount=discount, active=active)
            except Exception as exc:
                logger.warning("Failed to parse promo row: %s", exc)
        return promos

    def upsert_user(self, user_id: int, username: str, full_name: str) -> None:
        """Insert or update a user record."""
        ws = self._get_or_create_ws(
            "Users",
            [
                "user_id",
                "username",
                "full_name",
                "last_delivery_name",
                "last_delivery_address",
                "last_delivery_contact",
                "last_delivery_area",
                "updated_at",
            ],
        )
        records = self._safe_get_all_records(
            ws,
            [
                "user_id",
                "username",
                "full_name",
                "last_delivery_name",
                "last_delivery_address",
                "last_delivery_contact",
                "last_delivery_area",
                "updated_at",
            ],
        )
        now = dt.datetime.utcnow().isoformat()
        for idx, row in enumerate(records, start=2):
            if str(row.get("user_id")) == str(user_id):
                ws.update(
                    f"B{idx}:H{idx}",
                    [[username, full_name, row.get("last_delivery_name", ""), row.get("last_delivery_address", ""), row.get("last_delivery_contact", ""), row.get("last_delivery_area", ""), now]],
                )
                return
        ws.append_row([user_id, username, full_name, "", "", "", "", now])

    def update_last_delivery(self, user_id: int, name: str, address: str, contact: str, area: str) -> None:
        """Persist last delivery info for quick reuse."""
        ws = self._get_or_create_ws(
            "Users",
            [
                "user_id",
                "username",
                "full_name",
                "last_delivery_name",
                "last_delivery_address",
                "last_delivery_contact",
                "last_delivery_area",
                "updated_at",
            ],
        )
        records = self._safe_get_all_records(
            ws,
            [
                "user_id",
                "username",
                "full_name",
                "last_delivery_name",
                "last_delivery_address",
                "last_delivery_contact",
                "last_delivery_area",
                "updated_at",
            ],
        )
        now = dt.datetime.utcnow().isoformat()
        for idx, row in enumerate(records, start=2):
            if str(row.get("user_id")) == str(user_id):
                ws.update(
                    f"D{idx}:H{idx}",
                    [[name, address, contact, area, now]],
                )
                return
        ws.append_row([user_id, "", "", name, address, contact, area, now])

    def get_last_delivery(self, user_id: int) -> Optional[Dict[str, str]]:
        """Fetch last delivery info for a user."""
        ws = self._get_or_create_ws(
            "Users",
            [
                "user_id",
                "username",
                "full_name",
                "last_delivery_name",
                "last_delivery_address",
                "last_delivery_contact",
                "last_delivery_area",
                "updated_at",
            ],
        )
        records = self._safe_get_all_records(
            ws,
            [
                "user_id",
                "username",
                "full_name",
                "last_delivery_name",
                "last_delivery_address",
                "last_delivery_contact",
                "last_delivery_area",
                "updated_at",
            ],
        )
        for row in records:
            if str(row.get("user_id")) == str(user_id):
                name = row.get("last_delivery_name", "")
                address = row.get("last_delivery_address", "")
                contact = row.get("last_delivery_contact", "")
                area = row.get("last_delivery_area", "")
                if name and address and contact and area:
                    return {
                        "name": name,
                        "address": address,
                        "contact": contact,
                        "area": area,
                    }
        return None

    def log_order(self, order_data: Dict[str, Any]) -> None:
        """Write an order row to the next exact row in Orders sheet."""
        ws = self._get_or_create_ws("Orders", ORDER_HEADERS)
        row_values = [
            order_data.get("order_id"),
            order_data.get("created_at"),
            order_data.get("user_id"),
            order_data.get("username"),
            order_data.get("full_name"),
            json.dumps(order_data.get("items", [])),
            order_data.get("subtotal"),
            order_data.get("discount"),
            order_data.get("shipping"),
            order_data.get("total"),
            order_data.get("delivery_name"),
            order_data.get("delivery_address"),
            order_data.get("delivery_contact"),
            order_data.get("delivery_area"),
            order_data.get("payment_method"),
            order_data.get("payment_proof_file_id"),
            order_data.get("status"),
            order_data.get("tracking_number"),
        ]
        next_row = len(self._with_retry("orders_get_all_values", ws.get_all_values)) + 1
        end_cell = gspread.utils.rowcol_to_a1(next_row, len(row_values))
        self._with_retry(
            "orders_update",
            ws.update,
            range_name=f"A{next_row}:{end_cell}",
            values=[row_values],
        )

    def repair_orders_sheet(self) -> int:
        """Normalize shifted order rows so data starts at order_id column."""
        ws = self._get_or_create_ws("Orders", ORDER_HEADERS)
        values = ws.get_all_values()
        if not values:
            ws.update(range_name="A1", values=[ORDER_HEADERS])
            return 0

        order_id_pattern = re.compile(r"^DG\d{6}-\d{4,}-[A-Za-z0-9]+$")
        repaired_rows: List[List[str]] = [ORDER_HEADERS]
        fixed = 0

        for row in values[1:]:
            if not any(str(cell).strip() for cell in row):
                continue

            start_idx = None
            for idx, cell in enumerate(row):
                if order_id_pattern.match(str(cell).strip()):
                    start_idx = idx
                    break

            if start_idx is None:
                continue

            normalized = row[start_idx : start_idx + len(ORDER_HEADERS)]
            if len(normalized) < len(ORDER_HEADERS):
                normalized += [""] * (len(ORDER_HEADERS) - len(normalized))
            repaired_rows.append(normalized)
            if start_idx != 0:
                fixed += 1

        ws.clear()
        ws.update(range_name="A1", values=repaired_rows)
        return fixed

    def update_order_status(self, order_id: str, status: str, tracking_number: str = "") -> bool:
        """Update status and tracking for an order."""
        ws = self._get_or_create_ws(
            "Orders",
            [
                "order_id",
                "created_at",
                "user_id",
                "username",
                "full_name",
                "items_json",
                "subtotal",
                "discount",
                "shipping",
                "total",
                "delivery_name",
                "delivery_address",
                "delivery_contact",
                "delivery_area",
                "payment_method",
                "payment_proof_file_id",
                "status",
                "tracking_number",
            ],
        )
        records = self._safe_get_all_records(
            ws,
            [
                "order_id",
                "created_at",
                "user_id",
                "username",
                "full_name",
                "items_json",
                "subtotal",
                "discount",
                "shipping",
                "total",
                "delivery_name",
                "delivery_address",
                "delivery_contact",
                "delivery_area",
                "payment_method",
                "payment_proof_file_id",
                "status",
                "tracking_number",
            ],
        )
        target_order_id = self._normalize_order_id(order_id)
        for idx, row in enumerate(records, start=2):
            if self._normalize_order_id(row.get("order_id")) == target_order_id:
                ws.update(values=[[status, tracking_number]], range_name=f"Q{idx}:R{idx}")
                return True
        return False

    def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Return an order by order_id."""
        ws = self._get_or_create_ws(
            "Orders",
            [
                "order_id",
                "created_at",
                "user_id",
                "username",
                "full_name",
                "items_json",
                "subtotal",
                "discount",
                "shipping",
                "total",
                "delivery_name",
                "delivery_address",
                "delivery_contact",
                "delivery_area",
                "payment_method",
                "payment_proof_file_id",
                "status",
                "tracking_number",
            ],
        )
        records = self._safe_get_all_records(
            ws,
            [
                "order_id",
                "created_at",
                "user_id",
                "username",
                "full_name",
                "items_json",
                "subtotal",
                "discount",
                "shipping",
                "total",
                "delivery_name",
                "delivery_address",
                "delivery_contact",
                "delivery_area",
                "payment_method",
                "payment_proof_file_id",
                "status",
                "tracking_number",
            ],
        )
        target_order_id = self._normalize_order_id(order_id)
        for row in records:
            if self._normalize_order_id(row.get("order_id")) == target_order_id:
                return row
        return None

    def get_orders_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """Return all orders for a user."""
        ws = self._get_or_create_ws(
            "Orders",
            [
                "order_id",
                "created_at",
                "user_id",
                "username",
                "full_name",
                "items_json",
                "subtotal",
                "discount",
                "shipping",
                "total",
                "delivery_name",
                "delivery_address",
                "delivery_contact",
                "delivery_area",
                "payment_method",
                "payment_proof_file_id",
                "status",
                "tracking_number",
            ],
        )
        records = self._safe_get_all_records(
            ws,
            [
                "order_id",
                "created_at",
                "user_id",
                "username",
                "full_name",
                "items_json",
                "subtotal",
                "discount",
                "shipping",
                "total",
                "delivery_name",
                "delivery_address",
                "delivery_contact",
                "delivery_area",
                "payment_method",
                "payment_proof_file_id",
                "status",
                "tracking_number",
            ],
        )
        return [row for row in records if str(row.get("user_id")) == str(user_id)]

    def get_all_orders(self) -> List[Dict[str, Any]]:
        """Return all orders."""
        ws = self._get_or_create_ws("Orders", ORDER_HEADERS)
        return self._safe_get_all_records(ws, ORDER_HEADERS)

    def log_message_thread(self, data: Dict[str, Any]) -> None:
        """Persist an order/ticket conversation message."""
        ws = self._get_or_create_ws("Messages", MESSAGE_HEADERS)
        ws.append_row(
            [
                str(data.get("message_id") or uuid.uuid4())[:36],
                data.get("created_at") or dt.datetime.utcnow().isoformat(),
                data.get("order_id", ""),
                data.get("ticket_id", ""),
                data.get("user_id", ""),
                data.get("username", ""),
                data.get("sender_type", "system"),
                data.get("sender_name", ""),
                data.get("message", ""),
                data.get("telegram_message_id", ""),
                data.get("reply_to_message_id", ""),
                "true" if str(data.get("read_by_admin", "")).strip().lower() == "true" else "false",
            ]
        )

    def log_ticket(self, ticket_type: str, user_id: int, username: str, message: str) -> str:
        """Log a customer service or bulk order ticket."""
        ws = self._get_or_create_ws(
            "Tickets",
            ["ticket_id", "created_at", "type", "user_id", "username", "message", "status"],
        )
        ticket_id = str(uuid.uuid4())[:8]
        ws.append_row([ticket_id, dt.datetime.utcnow().isoformat(), ticket_type, user_id, username, message, "open"])
        return ticket_id

    def log_affiliate(self, data: Dict[str, Any]) -> None:
        """Log affiliate enrollment data."""
        ws = self._get_or_create_ws(
            "Affiliates",
            ["created_at", "user_id", "username", "twitter_or_telegram", "email", "contact", "subscriber_count"],
        )
        ws.append_row(
            [
                dt.datetime.utcnow().isoformat(),
                data.get("user_id"),
                data.get("username"),
                data.get("handle"),
                data.get("email"),
                data.get("contact"),
                data.get("subs"),
            ]
        )

    def log_broadcast(self, data: Dict[str, Any]) -> None:
        """Log a broadcast action."""
        ws = self._get_or_create_ws(
            "BroadcastLog",
            ["created_at", "admin_id", "message", "photo_file_id", "sent_count"],
        )
        ws.append_row([
            dt.datetime.utcnow().isoformat(),
            data.get("admin_id"),
            data.get("message"),
            data.get("photo_file_id"),
            data.get("sent_count"),
        ])

    def log_audit(
        self,
        action: str,
        actor_id: int,
        target_type: str,
        target_id: str,
        before_json: str,
        after_json: str,
        notes: str = "",
    ) -> None:
        """Write immutable audit row for admin/system actions."""
        ws = self._get_or_create_ws(
            "AuditLog",
            ["created_at", "action", "actor_id", "target_type", "target_id", "before_json", "after_json", "notes"],
        )
        ws.append_row(
            [dt.datetime.utcnow().isoformat(), action, actor_id, target_type, target_id, before_json, after_json, notes]
        )

    def get_order_audit(self, order_id: str) -> List[Dict[str, Any]]:
        """Get audit rows for an order target."""
        ws = self._get_or_create_ws(
            "AuditLog",
            ["created_at", "action", "actor_id", "target_type", "target_id", "before_json", "after_json", "notes"],
        )
        rows = self._safe_get_all_records(
            ws, ["created_at", "action", "actor_id", "target_type", "target_id", "before_json", "after_json", "notes"]
        )
        target_order_id = self._normalize_order_id(order_id)
        return [
            r
            for r in rows
            if str(r.get("target_type")) == "order"
            and self._normalize_order_id(r.get("target_id")) == target_order_id
        ]

    def add_loyalty_points(self, user_id: int, points: int, reason: str, order_id: str = "") -> int:
        """Append loyalty ledger row and return current balance."""
        ws = self._get_or_create_ws(
            "LoyaltyLedger",
            ["created_at", "user_id", "points_delta", "reason", "order_id"],
        )
        ws.append_row([dt.datetime.utcnow().isoformat(), user_id, points, reason, order_id])
        balance = self.get_loyalty_balance(user_id)
        self.upsert_points_summary(user_id, balance)
        return balance

    def get_loyalty_balance(self, user_id: int) -> int:
        ws = self._get_or_create_ws(
            "LoyaltyLedger",
            ["created_at", "user_id", "points_delta", "reason", "order_id"],
        )
        rows = self._safe_get_all_records(ws, ["created_at", "user_id", "points_delta", "reason", "order_id"])
        return sum(int(float(r.get("points_delta", 0) or 0)) for r in rows if str(r.get("user_id")) == str(user_id))

    def upsert_points_summary(self, user_id: int, balance: Optional[int] = None) -> None:
        headers = [
            "user_id",
            "current_points",
            "earned_points",
            "redeemed_points",
            "restored_points",
            "order_reward_count",
            "referral_reward_count",
            "updated_at",
        ]
        ws = self._get_or_create_ws("PointsSummary", headers)
        ledger_ws = self._get_or_create_ws(
            "LoyaltyLedger",
            ["created_at", "user_id", "points_delta", "reason", "order_id"],
        )
        rows = self._safe_get_all_records(ledger_ws, ["created_at", "user_id", "points_delta", "reason", "order_id"])
        earned = 0
        redeemed = 0
        restored = 0
        order_reward_count = 0
        referral_reward_count = 0
        current_balance = 0
        for row in rows:
            if str(row.get("user_id")) != str(user_id):
                continue
            delta = int(float(row.get("points_delta", 0) or 0))
            reason = str(row.get("reason", "")).strip()
            current_balance += delta
            if delta > 0:
                earned += delta
            if reason == "reward_redeemed":
                redeemed += abs(delta)
            elif reason == "reward_restored":
                restored += abs(delta)
            elif reason == "order_received":
                order_reward_count += 1
            elif reason.startswith("referral_success:"):
                referral_reward_count += 1
        if balance is None:
            balance = current_balance
        now = dt.datetime.utcnow().isoformat()
        records = self._safe_get_all_records(ws, headers)
        values = [[user_id, balance, earned, redeemed, restored, order_reward_count, referral_reward_count, now]]
        for idx, row in enumerate(records, start=2):
            if str(row.get("user_id")) == str(user_id):
                ws.update(range_name=f"A{idx}:H{idx}", values=values)
                return
        ws.append_row(values[0])

    def upsert_referral_summary(
        self,
        referrer_id: int,
        referred_user_id: int,
        status: str,
        reward_points: int = 0,
        rewarded_at: str = "",
        order_id: str = "",
    ) -> None:
        headers = [
            "referrer_id",
            "referred_user_id",
            "created_at",
            "status",
            "reward_points",
            "rewarded_at",
            "reward_order_id",
            "updated_at",
        ]
        ws = self._get_or_create_ws("ReferralSummary", headers)
        records = self._safe_get_all_records(ws, headers)
        now = dt.datetime.utcnow().isoformat()
        values = [[referrer_id, referred_user_id, now, status, reward_points, rewarded_at, order_id, now]]
        for idx, row in enumerate(records, start=2):
            if str(row.get("referrer_id")) == str(referrer_id) and str(row.get("referred_user_id")) == str(referred_user_id):
                created_at = str(row.get("created_at") or now)
                ws.update(
                    range_name=f"A{idx}:H{idx}",
                    values=[[referrer_id, referred_user_id, created_at, status, reward_points, rewarded_at, order_id, now]],
                )
                return
        ws.append_row(values[0])

    def rebuild_rewards_summaries(self) -> None:
        referral_headers = [
            "referrer_id",
            "referred_user_id",
            "created_at",
            "status",
            "reward_points",
            "rewarded_at",
            "reward_order_id",
            "updated_at",
        ]
        points_headers = [
            "user_id",
            "current_points",
            "earned_points",
            "redeemed_points",
            "restored_points",
            "order_reward_count",
            "referral_reward_count",
            "updated_at",
        ]
        ref_ws = self._get_or_create_ws("Referrals", ["user_id", "referrer_id", "created_at"])
        referral_summary_ws = self._get_or_create_ws("ReferralSummary", referral_headers)
        points_summary_ws = self._get_or_create_ws("PointsSummary", points_headers)
        ledger_ws = self._get_or_create_ws(
            "LoyaltyLedger",
            ["created_at", "user_id", "points_delta", "reason", "order_id"],
        )
        ref_rows = self._safe_get_all_records(ref_ws, ["user_id", "referrer_id", "created_at"])
        ledger_rows = self._safe_get_all_records(ledger_ws, ["created_at", "user_id", "points_delta", "reason", "order_id"])
        referral_summary_rows = [referral_headers]
        user_ids = set()
        for row in ref_rows:
            user_id = str(row.get("user_id", "")).strip()
            referrer_id = str(row.get("referrer_id", "")).strip()
            if not user_id or not referrer_id:
                continue
            user_ids.add(user_id)
            user_ids.add(referrer_id)
            rewarded = self.has_referral_reward(int(referrer_id), int(user_id))
            referral_summary_rows.append(
                [
                    referrer_id,
                    user_id,
                    row.get("created_at", ""),
                    "rewarded" if rewarded else "pending",
                    REFERRAL_SUCCESS_POINTS if rewarded else 0,
                    row.get("created_at", "") if rewarded else "",
                    "",
                    dt.datetime.utcnow().isoformat(),
                ]
            )
        for row in ledger_rows:
            uid = str(row.get("user_id", "")).strip()
            if uid:
                user_ids.add(uid)
        referral_summary_ws.clear()
        referral_summary_ws.update("A1", referral_summary_rows)
        points_summary_rows = [points_headers]
        for user_id in sorted(user_ids, key=lambda v: int(v) if str(v).isdigit() else v):
            balance = self.get_loyalty_balance(int(user_id))
            earned = redeemed = restored = order_reward_count = referral_reward_count = 0
            for row in ledger_rows:
                if str(row.get("user_id")) != str(user_id):
                    continue
                delta = int(float(row.get("points_delta", 0) or 0))
                reason = str(row.get("reason", "")).strip()
                if delta > 0:
                    earned += delta
                if reason == "reward_redeemed":
                    redeemed += abs(delta)
                elif reason == "reward_restored":
                    restored += abs(delta)
                elif reason == "order_received":
                    order_reward_count += 1
                elif reason.startswith("referral_success:"):
                    referral_reward_count += 1
            points_summary_rows.append(
                [user_id, balance, earned, redeemed, restored, order_reward_count, referral_reward_count, dt.datetime.utcnow().isoformat()]
            )
        points_summary_ws.clear()
        points_summary_ws.update("A1", points_summary_rows)

    def has_loyalty_entry(self, user_id: int, reason: str, order_id: str = "") -> bool:
        ws = self._get_or_create_ws(
            "LoyaltyLedger",
            ["created_at", "user_id", "points_delta", "reason", "order_id"],
        )
        rows = self._safe_get_all_records(ws, ["created_at", "user_id", "points_delta", "reason", "order_id"])
        for row in rows:
            if str(row.get("user_id")) != str(user_id):
                continue
            if str(row.get("reason", "")).strip() != reason:
                continue
            if order_id and str(row.get("order_id", "")).strip() != str(order_id):
                continue
            return True
        return False

    def has_referral_reward(self, referrer_id: int, referred_user_id: int) -> bool:
        return self.has_loyalty_entry(referrer_id, f"referral_success:{referred_user_id}")

    def redeem_loyalty_points(self, user_id: int, points: int, order_id: str) -> int:
        if points <= 0:
            return self.get_loyalty_balance(user_id)
        if self.has_loyalty_entry(user_id, "reward_redeemed", order_id):
            return self.get_loyalty_balance(user_id)
        return self.add_loyalty_points(user_id, -points, "reward_redeemed", order_id)

    def restore_redeemed_loyalty_points(self, user_id: int, order_id: str) -> int:
        ws = self._get_or_create_ws(
            "LoyaltyLedger",
            ["created_at", "user_id", "points_delta", "reason", "order_id"],
        )
        rows = self._safe_get_all_records(ws, ["created_at", "user_id", "points_delta", "reason", "order_id"])
        redeemed = 0
        restored = 0
        for row in rows:
            if str(row.get("user_id")) != str(user_id):
                continue
            if str(row.get("order_id", "")).strip() != str(order_id):
                continue
            reason = str(row.get("reason", "")).strip()
            points = int(float(row.get("points_delta", 0) or 0))
            if reason == "reward_redeemed":
                redeemed += abs(points)
            elif reason == "reward_restored":
                restored += abs(points)
        missing = redeemed - restored
        if missing <= 0:
            return self.get_loyalty_balance(user_id)
        return self.add_loyalty_points(user_id, missing, "reward_restored", order_id)

    def set_referrer(self, user_id: int, referrer_id: int) -> bool:
        """Assign a referrer once. Returns False if already set."""
        ws = self._get_or_create_ws("Referrals", ["user_id", "referrer_id", "created_at"])
        rows = self._safe_get_all_records(ws, ["user_id", "referrer_id", "created_at"])
        for r in rows:
            if str(r.get("user_id")) == str(user_id):
                return False
        created_at = dt.datetime.utcnow().isoformat()
        ws.append_row([user_id, referrer_id, created_at])
        self.upsert_referral_summary(referrer_id, user_id, "pending")
        return True

    def get_referrer(self, user_id: int) -> Optional[int]:
        ws = self._get_or_create_ws("Referrals", ["user_id", "referrer_id", "created_at"])
        rows = self._safe_get_all_records(ws, ["user_id", "referrer_id", "created_at"])
        for r in rows:
            if str(r.get("user_id")) == str(user_id):
                rid = str(r.get("referrer_id", "")).strip()
                if rid.lstrip("-").isdigit():
                    return int(rid)
        return None

    def upsert_group(self, chat_id: int, title: str, chat_type: str) -> None:
        """Insert or update a Telegram group record."""
        ws = self._get_or_create_ws("Groups", ["chat_id", "title", "chat_type", "updated_at"])
        records = self._safe_get_all_records(ws, ["chat_id", "title", "chat_type", "updated_at"])
        now = dt.datetime.utcnow().isoformat()
        for idx, row in enumerate(records, start=2):
            if str(row.get("chat_id")) == str(chat_id):
                ws.update(range_name=f"B{idx}:D{idx}", values=[[title, chat_type, now]])
                return
        ws.append_row([chat_id, title, chat_type, now])

    def list_groups(self) -> List[Dict[str, Any]]:
        """Return all saved group chats."""
        ws = self._get_or_create_ws("Groups", ["chat_id", "title", "chat_type", "updated_at"])
        return self._safe_get_all_records(ws, ["chat_id", "title", "chat_type", "updated_at"])

    def upsert_channel(self, chat_id: int, title: str) -> None:
        """Insert or update a Telegram channel record."""
        ws = self._get_or_create_ws("Channels", ["chat_id", "title", "updated_at"])
        records = self._safe_get_all_records(ws, ["chat_id", "title", "updated_at"])
        now = dt.datetime.utcnow().isoformat()
        for idx, row in enumerate(records, start=2):
            if str(row.get("chat_id")) == str(chat_id):
                ws.update(range_name=f"B{idx}:C{idx}", values=[[title, now]])
                return
        ws.append_row([chat_id, title, now])

    def list_channels(self) -> List[Dict[str, Any]]:
        """Return all saved channels."""
        ws = self._get_or_create_ws("Channels", ["chat_id", "title", "updated_at"])
        return self._safe_get_all_records(ws, ["chat_id", "title", "updated_at"])

    def upsert_group_member(
        self,
        group_id: int,
        group_title: str,
        user_id: int,
        username: str,
        full_name: str,
        status: str,
    ) -> None:
        """Insert or update a known member for a group."""
        headers = ["group_id", "group_title", "user_id", "username", "full_name", "status", "updated_at"]
        ws = self._get_or_create_ws("GroupMembers", headers)
        now = dt.datetime.utcnow().isoformat()
        try:
            records = self._safe_get_all_records(ws, headers)
        except Exception as exc:
            logger.warning("upsert_group_member fallback append for %s/%s: %s", group_id, user_id, exc)
            ws.append_row([group_id, group_title, user_id, username, full_name, status, now])
            return
        for idx, row in enumerate(records, start=2):
            if str(row.get("group_id")) == str(group_id) and str(row.get("user_id")) == str(user_id):
                ws.update(range_name=f"D{idx}:G{idx}", values=[[username, full_name, status, now]])
                return
        ws.append_row([group_id, group_title, user_id, username, full_name, status, now])

    def list_group_members(self, group_id: int) -> List[Dict[str, Any]]:
        """Return known members for a given group."""
        headers = ["group_id", "group_title", "user_id", "username", "full_name", "status", "updated_at"]
        ws = self._get_or_create_ws("GroupMembers", headers)
        records = self._safe_get_all_records(ws, headers)
        return [r for r in records if str(r.get("group_id")) == str(group_id)]


async def get_sheets(context: ContextTypes.DEFAULT_TYPE) -> SheetsClient:
    """Return a cached SheetsClient."""
    if "sheets" not in context.application.bot_data:
        context.application.bot_data["sheets"] = await asyncio.to_thread(SheetsClient)
    return context.application.bot_data["sheets"]


def _safe_json(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return "{}"


def _is_negative_order_status(status: str) -> bool:
    return str(status or "").strip().lower() in {"rejected", "cancelled", "canceled"}


def compute_reward_redemption(balance: int, subtotal_after_promo: float) -> Tuple[int, float]:
    """Return points and peso value to auto-redeem for this checkout."""
    if balance < LOYALTY_REDEEM_POINTS or subtotal_after_promo < LOYALTY_REDEEM_VALUE:
        return 0, 0.0
    blocks = min(balance // LOYALTY_REDEEM_POINTS, int(subtotal_after_promo // LOYALTY_REDEEM_VALUE))
    return blocks * LOYALTY_REDEEM_POINTS, float(blocks * LOYALTY_REDEEM_VALUE)


async def calculate_discount_breakdown(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    promo_code: str,
    subtotal: float,
) -> Dict[str, Any]:
    sheets = await get_sheets(context)
    promos = await asyncio.to_thread(sheets.get_promos)
    promo_discount = 0.0
    code = str(promo_code or "").strip()
    if code and code.lower() != "none":
        promo = promos.get(code.upper())
        if promo and promo.active:
            promo_discount = min(float(promo.discount), subtotal)
    loyalty_balance = await asyncio.to_thread(sheets.get_loyalty_balance, user_id)
    reward_points_used, reward_discount = compute_reward_redemption(loyalty_balance, max(subtotal - promo_discount, 0.0))
    return {
        "promo_discount": promo_discount,
        "reward_points_used": reward_points_used,
        "reward_discount": reward_discount,
        "discount": promo_discount + reward_discount,
        "loyalty_balance": loyalty_balance,
    }


async def award_received_rewards(
    context: ContextTypes.DEFAULT_TYPE,
    order: Dict[str, Any],
) -> Tuple[int, bool]:
    sheets = await get_sheets(context)
    user_id = int(order.get("user_id"))
    order_id = str(order.get("order_id"))
    if await asyncio.to_thread(sheets.has_loyalty_entry, user_id, "order_received", order_id):
        balance = await asyncio.to_thread(sheets.get_loyalty_balance, user_id)
    else:
        balance = await asyncio.to_thread(
            sheets.add_loyalty_points, user_id, LOYALTY_POINTS_PER_ORDER, "order_received", order_id
        )
    referrer_id = await asyncio.to_thread(sheets.get_referrer, user_id)
    referral_awarded = False
    if referrer_id and not await asyncio.to_thread(sheets.has_referral_reward, referrer_id, user_id):
        await asyncio.to_thread(
            sheets.add_loyalty_points,
            referrer_id,
            REFERRAL_SUCCESS_POINTS,
            f"referral_success:{user_id}",
            order_id,
        )
        await asyncio.to_thread(
            sheets.upsert_referral_summary,
            referrer_id,
            user_id,
            "rewarded",
            REFERRAL_SUCCESS_POINTS,
            dt.datetime.utcnow().isoformat(),
            order_id,
        )
        referral_awarded = True
    return balance, referral_awarded


async def set_order_status_with_audit(
    context: ContextTypes.DEFAULT_TYPE,
    order_id: str,
    status: str,
    tracking_number: str,
    actor_id: int,
    action: str,
    notes: str = "",
) -> bool:
    """Update order status and write an audit entry."""
    sheets = await get_sheets(context)
    before = await asyncio.to_thread(sheets.get_order_by_id, order_id)
    updated = await asyncio.to_thread(sheets.update_order_status, order_id, status, tracking_number)
    if not updated:
        return False
    after = await asyncio.to_thread(sheets.get_order_by_id, order_id)
    restore_note = ""
    if after and _is_negative_order_status(status):
        user_id_raw = str(after.get("user_id", "")).strip()
        if user_id_raw.isdigit():
            had_restore_entry = await asyncio.to_thread(sheets.has_loyalty_entry, int(user_id_raw), "reward_restored", order_id)
            restored_balance = await asyncio.to_thread(sheets.restore_redeemed_loyalty_points, int(user_id_raw), order_id)
            has_restore_entry = await asyncio.to_thread(sheets.has_loyalty_entry, int(user_id_raw), "reward_restored", order_id)
            if has_restore_entry and not had_restore_entry:
                restore_note = f" loyalty_balance={restored_balance}"
                try:
                    await context.bot.send_message(
                        chat_id=int(user_id_raw),
                        text=f"Your redeemed loyalty points for order {order_id} were returned to your balance.",
                    )
                except Exception as exc:
                    logger.warning("Failed to notify loyalty restoration for %s: %s", order_id, exc)
    await asyncio.to_thread(
        sheets.log_audit,
        action,
        actor_id,
        "order",
        order_id,
        _safe_json(before or {}),
        _safe_json(after or {}),
        f"{notes}{restore_note}".strip(),
    )
    return True


async def schedule_abandoned_cart_reminder(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    """Schedule a single abandoned-cart reminder job."""
    if not context.job_queue:
        return
    job_name = f"abandoned_cart:{user_id}"
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()
    context.job_queue.run_once(
        abandoned_cart_reminder_job,
        when=ABANDONED_CART_REMINDER_MINUTES * 60,
        chat_id=chat_id,
        user_id=user_id,
        name=job_name,
        data={"user_id": user_id},
    )


def clear_abandoned_cart_reminder(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    if not context.job_queue:
        return
    job_name = f"abandoned_cart:{user_id}"
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()


async def abandoned_cart_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send reminder if user still has cart items."""
    user_id = context.job.data.get("user_id") if context.job and context.job.data else None
    if user_id is None:
        return
    udata = context.application.user_data.get(user_id, {})
    cart = udata.get("cart", {})
    if cart:
        try:
            await context.bot.send_message(
                chat_id=context.job.chat_id,
                text="You left items in your cart. Complete checkout before stock runs out. 🛒",
            )
        except Exception as exc:
            logger.warning("Failed abandoned cart reminder to %s: %s", user_id, exc)


async def schedule_post_purchase_followup(context: ContextTypes.DEFAULT_TYPE, user_id: int, order_id: str) -> None:
    """Schedule post-purchase follow-up message."""
    if not context.job_queue:
        return
    context.job_queue.run_once(
        post_purchase_followup_job,
        when=24 * 60 * 60,
        chat_id=user_id,
        data={"order_id": order_id},
    )


async def post_purchase_followup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    order_id = context.job.data.get("order_id") if context.job and context.job.data else ""
    try:
        await context.bot.send_message(
            chat_id=context.job.chat_id,
            text=f"How was your order {order_id}? Reply anytime if you need support, a reorder, or help with anything else from Daddy Grab.",
        )
    except Exception as exc:
        logger.warning("Follow-up send failed for %s: %s", context.job.chat_id, exc)


async def send_photo_or_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_path: str,
    text: str,
    reply_markup: Optional[ReplyKeyboardMarkup] = None,
    parse_mode: Optional[str] = None,
) -> None:
    """Send a local photo with caption, or fallback to text if missing."""
    try:
        if image_path:
            if not os.path.isabs(image_path):
                base_dir = os.path.dirname(os.path.abspath(__file__))
                image_path = os.path.join(base_dir, image_path)
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                )
                return
    except Exception as exc:
        logger.warning("Failed to send image %s: %s", image_path, exc)
    await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)


def is_admin(user_id: int) -> bool:
    """Check if user is an admin."""
    return user_id in ADMIN_IDS


def parse_customer_chat_id(order: Dict[str, Any]) -> Optional[int]:
    """Return Telegram chat ID when the stored order user_id is numeric."""
    raw = str(order.get("user_id", "")).strip()
    if raw.lstrip("-").isdigit():
        return int(raw)
    return None


def parse_forward_target_from_admin_message(text: str) -> Tuple[Optional[int], str]:
    """Extract Telegram user id and optional order/ticket reference from an admin-group bot message."""
    if not text:
        return None, ""
    user_match = re.search(r"(?:User ID|Telegram ID):\s*(-?\d+)", text, re.IGNORECASE)
    target_user_id = int(user_match.group(1)) if user_match else None
    ref_match = re.search(r"(?:Order|Ticket)\s*[:#]?\s*([A-Z0-9\-]{6,})", text, re.IGNORECASE)
    reference = ref_match.group(1).strip() if ref_match else ""
    return target_user_id, reference


def parse_thread_reference_from_bot_message(text: str) -> str:
    """Extract order reference from a bot message when customers reply in private chat."""
    if not text:
        return ""
    ref_match = re.search(r"Order\s*[:#]?\s*([A-Z0-9\-]{6,})", text, re.IGNORECASE)
    return ref_match.group(1).strip() if ref_match else ""


def extract_thread_message_text(message) -> str:
    """Normalize customer/admin message content for the thread log."""
    if getattr(message, "text", None):
        return message.text.strip()
    if getattr(message, "caption", None):
        prefix = "[Photo]" if getattr(message, "photo", None) else "[Attachment]"
        return f"{prefix} {message.caption.strip()}".strip()
    if getattr(message, "photo", None):
        return "[Photo]"
    if getattr(message, "document", None):
        return f"[Document] {getattr(message.document, 'file_name', '')}".strip()
    return ""


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Build the main menu keyboard."""
    return ReplyKeyboardMarkup(
        [
            ["🛍️ Catalogue", "🔎 Track Order"],
            ["💬 Contact Admin", "📦 Bulk Orders"],
            ["🎁 Refer a Friend", "🤝 Affiliate Enrollment"],
        ],
        resize_keyboard=True,
    )


def ordering_keyboard() -> ReplyKeyboardMarkup:
    """Build the ordering keyboard."""
    return ReplyKeyboardMarkup(
        [["🛒 View Cart", "✅ Checkout"], ["↩️ Back to Menu"]], resize_keyboard=True
    )


def yes_no_keyboard() -> ReplyKeyboardMarkup:
    """Build a yes/no keyboard."""
    return ReplyKeyboardMarkup([["✅ Yes", "❌ No"]], resize_keyboard=True, one_time_keyboard=True)


def payment_keyboard() -> ReplyKeyboardMarkup:
    """Build the payment method keyboard."""
    return ReplyKeyboardMarkup(
        [["💳 E-Wallet", "🏦 Bank Transfer"], ["💵 Cash on Delivery"], ["↩️ Back to Menu"]],
        resize_keyboard=True,
    )


def delivery_area_keyboard() -> ReplyKeyboardMarkup:
    """Build the delivery area keyboard."""
    return ReplyKeyboardMarkup(
        [["🌆 Metro Manila", "🌏 Outside Metro Manila"], ["↩️ Back to Menu"]],
        resize_keyboard=True,
    )


def track_keyboard() -> ReplyKeyboardMarkup:
    """Build the tracking choice keyboard."""
    return ReplyKeyboardMarkup(
        [["🔢 By Order Number", "🆔 By My Telegram ID"], ["↩️ Back to Menu"]],
        resize_keyboard=True,
    )


def referral_share_keyboard(uid: int) -> InlineKeyboardMarkup:
    """Build share/open buttons for the user's referral link."""
    referral_link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    share_text = parse.quote(
        f"Order here and use my referral link to join the rewards program: {referral_link}"
    )
    share_url = f"https://t.me/share/url?url={parse.quote(referral_link)}&text={share_text}"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎁 Open My Link", url=referral_link),
                InlineKeyboardButton("📤 Share Link", url=share_url),
            ]
        ]
    )


def catalogue_redirect_keyboard() -> InlineKeyboardMarkup:
    """Link users to the hosted catalogue/AI agent page."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Open Daddy Grab", web_app=WebAppInfo(url=DADDY_GRAB_MINIAPP_URL))]]
    )


def admin_tools_keyboard() -> InlineKeyboardMarkup:
    """Link admins to the hosted admin console."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Open Admin Tools", url=DADDY_GRAB_ADMIN_URL)]]
    )


def miniapp_redirect_message(action: str = "continue") -> str:
    """Return consistent redirect copy for storefront actions."""
    if action == "support":
        return "Need help? Open the Daddy Grab Mini App and use support chat so the team can assist you faster."
    if action == "bulk":
        return "Bulk orders are handled in the Daddy Grab Mini App. Open it below and send your product list, quantities, and target date."
    if action == "rewards":
        return "Rewards and referrals now live in the Daddy Grab Mini App. Open it below to check your perks."
    if action == "affiliate":
        return "Affiliate sign-ups are handled in the Daddy Grab Mini App. Open it below and use support chat to get started."
    if action == "track":
        return "Order tracking is available in the Daddy Grab Mini App. Open it below to check your latest order."
    return "Daddy Grab is your one-stop shop for products and services. Open the Mini App below to browse, order, and get support."


def build_catalog_keyboard(products: List[Product]) -> InlineKeyboardMarkup:
    """Create inline buttons for catalog add/remove."""
    rows = []
    for p in products:
        rows.append(
            [
                InlineKeyboardButton(f"Add {p.sku}", callback_data=f"add:{p.sku}"),
                InlineKeyboardButton(f"Remove {p.sku}", callback_data=f"remove:{p.sku}"),
            ]
        )
    rows.append([InlineKeyboardButton("View Cart", callback_data="view_cart")])
    return InlineKeyboardMarkup(rows)


def build_product_detail_keyboard(sku: str, category: str) -> InlineKeyboardMarkup:
    """Create inline buttons for a single product detail view."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Add 1", callback_data=f"add:{sku}"),
                InlineKeyboardButton("✍️ Qty", callback_data=f"qty:{sku}"),
            ],
            [InlineKeyboardButton("🛒 View Cart", callback_data="cart:view")],
            [InlineKeyboardButton("↩️ Back to Category", callback_data=f"cat:{category}")],
        ]
    )


def build_cart_keyboard(cart: Dict[str, int], products_map: Dict[str, Product]) -> Optional[InlineKeyboardMarkup]:
    """Build a richer cart UI with per-item quantity editing."""
    if not cart:
        return None
    rows: List[List[InlineKeyboardButton]] = []
    for sku, qty in cart.items():
        product = products_map.get(sku)
        title = product.name if product else sku
        rows.append([InlineKeyboardButton(f"🧾 {title}", callback_data="noop")])
        rows.append(
            [
                InlineKeyboardButton("➖", callback_data=f"cartdec:{sku}"),
                InlineKeyboardButton(f"{qty}", callback_data="noop"),
                InlineKeyboardButton("➕", callback_data=f"cartinc:{sku}"),
                InlineKeyboardButton("🗑️ Remove", callback_data=f"cartdel:{sku}"),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("✅ Checkout", callback_data="cart:checkout"),
            InlineKeyboardButton("↩️ Back", callback_data="cart:back"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def format_catalog(products: List[Product]) -> str:
    """Format catalog text."""
    lines = ["*Daddy Grab catalog*", "Please select your products:"]
    for p in products:
        lines.append(f"• `{p.sku}` — {p.name} — ₱{p.price:.2f}")
    return "\n".join(lines)


def format_cart(cart: Dict[str, int], products_map: Dict[str, Product]) -> Tuple[str, float]:
    """Format cart summary and return subtotal."""
    if not cart:
        return "Your cart is still empty. Add something first to continue.", 0.0
    lines = ["*🛒 Your cart*", ""]
    subtotal = 0.0
    for sku, qty in cart.items():
        product = products_map.get(sku)
        if not product:
            continue
        line_total = product.price * qty
        subtotal += line_total
        lines.append(f"• {product.name} x{qty} — ₱{line_total:.2f}")
    lines.append("")
    lines.append(f"Subtotal: ₱{subtotal:.2f} 💰")
    if sum(cart.values()) >= WHOLESALE_THRESHOLD:
        lines.append("Wholesale threshold reached. You will be prioritized by the team. ⚡")
    return "\n".join(lines), subtotal


async def send_product_detail(
    message_target,
    product: Product,
    category: str,
) -> None:
    """Send a single product detail card with image, description, and price."""
    description = product.description or "No description yet."
    caption = f"*{product.name}*\n{description}\nPrice: ₱{product.price:.2f}"
    try:
        if product.image_url:
            await message_target.reply_photo(
                photo=product.image_url,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=build_product_detail_keyboard(product.sku, category),
            )
        else:
            await message_target.reply_text(
                caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=build_product_detail_keyboard(product.sku, category),
            )
    except Exception as exc:
        logger.warning("Failed to send product detail for %s: %s", product.sku, exc)
        await message_target.reply_text(
            caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=build_product_detail_keyboard(product.sku, category),
        )


async def show_cart(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    cart: Dict[str, int],
    products_map: Dict[str, Product],
    force_new: bool = False,
) -> None:
    """Display the cart summary with inline quantity controls, editing in place when possible."""
    summary, _ = format_cart(cart, products_map)
    keyboard = build_cart_keyboard(cart, products_map)
    message_id = context.user_data.get("cart_message_id")

    if message_id and not force_new:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=summary,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
            )
            return
        except Exception as exc:
            logger.warning("Failed to edit cart message: %s", exc)

    sent = await context.bot.send_message(
        chat_id=chat_id,
        text=summary,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )
    context.user_data["cart_message_id"] = sent.message_id


def build_category_keyboard(categories: List[str]) -> InlineKeyboardMarkup:
    """Build inline category selection."""
    rows = [[InlineKeyboardButton(f"✨ {c}", callback_data=f"cat:{c}")] for c in categories]
    rows.append([InlineKeyboardButton("🛒 View Cart", callback_data="cart:view")])
    return InlineKeyboardMarkup(rows)


def build_product_list_keyboard(category: str, products: List[Product]) -> InlineKeyboardMarkup:
    """Build inline product list for a category (name only)."""
    rows = [[InlineKeyboardButton(f"{p.name}", callback_data=f"prod:{p.sku}")] for p in products]
    rows.append([InlineKeyboardButton("↩️ Back to Categories", callback_data="catlist")])
    rows.append([InlineKeyboardButton("🛒 View Cart", callback_data="cart:view")])
    return InlineKeyboardMarkup(rows)


def products_by_category(products: List[Product]) -> Dict[str, List[Product]]:
    """Group products by category."""
    grouped: Dict[str, List[Product]] = {}
    for p in products:
        grouped.setdefault(p.category, []).append(p)
    return grouped


def compute_totals(subtotal: float, discount: float, area: str, payment_method: str) -> Tuple[float, float, float]:
    """Compute discount, shipping, and total."""
    shipping = SHIPPING_PROVINCIAL if area == "Outside Metro Manila" else 0.0
    cod_fee = COD_FEE if payment_method == "Cash on Delivery" else 0.0
    total = max(subtotal - discount, 0.0) + shipping + cod_fee
    return discount, shipping + cod_fee, total


def payment_instructions(method: str) -> str:
    """Return payment instructions for selected method."""
    if method == "E-Wallet":
        return (
            "Payment via E‑Wallet:\n"
            "• Type: GCash\n"
            "  Acct Number: 09088960308\n"
            "  Acct Name: Jo***a B.\n\n"
            "• Type: Maya\n"
            "  Acct Number: 09959850349\n"
            "  Acct Name: Joshua Banta"
        )
    if method == "Bank Transfer":
        return (
            "Payment via Bank Transfer:\n"
            "• Bank: Gotyme\n"
            "• Acct Number: 016301929833\n"
            "• Acct Name: Joshua Banta"
        )
    return (
        "Cash on Delivery:\n"
        f"• Additional ₱{int(COD_FEE)} COD fee will be added to your invoice."
    )


def build_invoice(order: Dict[str, Any]) -> str:
    """Build a text invoice summary."""
    items = order.get("items", [])
    promo_discount = float(order.get("promo_discount", 0) or 0)
    reward_discount = float(order.get("reward_discount", 0) or 0)
    reward_points_used = int(float(order.get("reward_points_used", 0) or 0))
    current_points = order.get("current_points")
    lines = [
        f"*Order #{order.get('order_id')}*",
        f"Status: {order.get('status')}",
        "",
        "Items:",
    ]
    for item in items:
        lines.append(f"• {item['name']} x{item['qty']} — ₱{item['line_total']:.2f}")
    lines.extend(
        [
            "",
            f"Subtotal: ₱{order.get('subtotal'):.2f}",
            f"Promo Discount: ₱{promo_discount:.2f}",
            f"Loyalty Auto-Redemption: ₱{reward_discount:.2f} ({reward_points_used} pts)",
            f"Total Discount: ₱{order.get('discount'):.2f}",
            f"Shipping: ₱{order.get('shipping'):.2f}",
            f"Total: ₱{order.get('total'):.2f}",
            "",
            f"Delivery: {order.get('delivery_name')} — {order.get('delivery_contact')}",
            f"Address: {order.get('delivery_address')}",
        ]
    )
    if current_points is not None:
        lines.extend(["", f"Current Points: {int(float(current_points or 0))} pts"])
    return "\n".join(lines)


def build_checkout_preview(
    items: List[Dict[str, Any]],
    subtotal: float,
    promo_discount: float,
    reward_discount: float,
    reward_points_used: int,
    loyalty_balance: int,
    area: str,
    delivery_name: str,
    delivery_address: str,
    delivery_contact: str,
) -> str:
    """Show what the customer will pay before selecting a payment method."""
    discount = promo_discount + reward_discount
    _, transfer_shipping, transfer_total = compute_totals(subtotal, discount, area, "Bank Transfer")
    _, cod_shipping, cod_total = compute_totals(subtotal, discount, area, "Cash on Delivery")
    lines = ["*Order Summary*", "", "Items:"]
    for item in items:
        lines.append(f"• {item['name']} x{item['qty']} — ₱{item['line_total']:.2f}")
    lines.extend(
        [
            "",
            f"Subtotal: ₱{subtotal:.2f}",
            f"Promo Discount: ₱{promo_discount:.2f}",
            f"Auto Loyalty Discount: ₱{reward_discount:.2f} ({reward_points_used} pts)",
            f"Total Discount: ₱{discount:.2f}",
            f"Shipping: ₱{transfer_shipping:.2f}",
            f"E-Wallet / Bank Transfer Total: ₱{transfer_total:.2f}",
            f"Cash on Delivery Total: ₱{cod_total:.2f}",
            f"Current Points: {loyalty_balance} pts",
            "",
            "Delivery Details:",
            f"{delivery_name} — {delivery_contact}",
            delivery_address,
            f"Area: {area}",
        ]
    )
    return "\n".join(lines)


async def send_checkout_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Compute and send the pre-payment checkout summary."""
    cart = context.user_data.get("cart", {})
    products_map: Dict[str, Product] = context.user_data.get("products", {})
    items = []
    subtotal = 0.0
    for sku, qty in cart.items():
        product = products_map.get(sku)
        if not product:
            continue
        line_total = product.price * qty
        subtotal += line_total
        items.append({"sku": sku, "name": product.name, "qty": qty, "line_total": line_total})
    if not items:
        return
    discount_meta = await calculate_discount_breakdown(
        context,
        update.effective_user.id,
        str(context.user_data.get("promo_code", "")).strip(),
        subtotal,
    )
    preview = build_checkout_preview(
        items,
        subtotal,
        discount_meta["promo_discount"],
        discount_meta["reward_discount"],
        discount_meta["reward_points_used"],
        discount_meta["loyalty_balance"],
        context.user_data.get("delivery_area", "Metro Manila"),
        context.user_data.get("delivery_name", ""),
        context.user_data.get("delivery_address", ""),
        context.user_data.get("delivery_contact", ""),
    )
    await update.message.reply_text(preview, parse_mode=ParseMode.MARKDOWN)


async def open_catalog_product_by_sku(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    sku: str,
) -> int:
    """Redirect deep links to the hosted catalogue experience."""
    await message.reply_text(
        "Your pick is waiting in the Mini App. Open it below and let the fun begin. 😘",
        reply_markup=catalogue_redirect_keyboard(),
    )
    return MENU


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: show privacy disclaimer and ask consent."""
    user = update.effective_user
    sheets = await get_sheets(context)
    await asyncio.to_thread(sheets.upsert_user, user.id, user.username or "", user.full_name)
    # Referral entry via /start ref_123456789
    if context.args:
        token = str(context.args[0]).strip().lower()
        if token.startswith("ref_"):
            rid = token.replace("ref_", "", 1)
            if rid.isdigit() and int(rid) != user.id:
                applied = await asyncio.to_thread(sheets.set_referrer, user.id, int(rid))
                if applied:
                    await update.message.reply_text("Referral applied. You can start earning loyalty rewards. 🎁")
        elif token.startswith("catalog_"):
            context.user_data["pending_catalog_sku"] = token.replace("catalog_", "", 1).upper()
    text = textwrap.dedent(
        """
        Welcome to *Daddy Grab Super App*.

Tap the Mini App button below to browse product lines, place orders, and manage support in one place.

        Before we continue, here’s the important bit:
        • We store order details and delivery info for fulfillment.
        • Payment proof images are kept for verification.
        • You can request deletion anytime.

        Do you agree to continue?
        """
    ).strip()
    await send_photo_or_text(
        update,
        context,
        START_IMAGE_PATH,
        text,
        reply_markup=yes_no_keyboard(),
        parse_mode=ParseMode.MARKDOWN,
    )
    return CONSENT


async def consent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle consent response."""
    choice = update.message.text.strip().lower()
    if "yes" in choice:
        pending_sku = context.user_data.pop("pending_catalog_sku", "")
        if pending_sku:
            await update.message.reply_text("Perfect. We’re opening your selected item now.")
            return await open_catalog_product_by_sku(update.message, context, pending_sku)
        await update.message.reply_text(
            "You’re all set.\nTap *Catalogue* to open the Mini App and place your order.\nNeed help? Tap *Contact Admin*.",
            reply_markup=main_menu_keyboard(),
            parse_mode=ParseMode.MARKDOWN,
        )
        await update.message.reply_text(
            "Daddy Grab is ready when you are. Tap below to continue.",
            reply_markup=main_menu_keyboard(),
        )
        return MENU
    await update.message.reply_text(
        "No problem. If you want to come back later, send /start anytime.", reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Route main menu selections."""
    text = update.message.text.strip()
    if "Catalogue" in text or "Ordering" in text:
        return await ordering_start(update, context)
    if "Track Order" in text:
        await update.message.reply_text(
            miniapp_redirect_message("track"),
            reply_markup=catalogue_redirect_keyboard(),
        )
        return MENU
    if "Contact Admin" in text or "Customer Service" in text:
        await update.message.reply_text(
            miniapp_redirect_message("support"),
            reply_markup=catalogue_redirect_keyboard(),
        )
        return MENU
    if "Bulk Orders" in text:
        await update.message.reply_text(
            miniapp_redirect_message("bulk"),
            reply_markup=catalogue_redirect_keyboard(),
        )
        return MENU
    if "Refer a Friend" in text:
        await update.message.reply_text(
            miniapp_redirect_message("rewards"),
            reply_markup=catalogue_redirect_keyboard(),
        )
        return MENU
    if "Affiliate Enrollment" in text:
        await update.message.reply_text(
            miniapp_redirect_message("affiliate"),
            reply_markup=catalogue_redirect_keyboard(),
        )
        return MENU
    await update.message.reply_text("Pick one of the buttons below to continue.", reply_markup=main_menu_keyboard())
    return MENU


async def ordering_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Redirect ordering requests to the hosted catalogue/AI experience."""
    await update.message.reply_text(
        miniapp_redirect_message(),
        reply_markup=catalogue_redirect_keyboard(),
    )
    return MENU


async def catalog_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Redirect any legacy inline catalogue callbacks to the hosted page."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        miniapp_redirect_message(),
        reply_markup=catalogue_redirect_keyboard(),
    )
    return MENU


async def ordering_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle ordering menu choices."""
    text = update.message.text.strip()
    if "cancel" in text.lower():
        return await cancel(update, context)
    if "View Cart" in text:
        cart = context.user_data.get("cart", {})
        products_map = context.user_data.get("products", {})
        await show_cart(context, update.effective_chat.id, cart, products_map)
        return ORDERING
    if "Checkout" in text:
        return await checkout_start(update, context)
    if "Back to Menu" in text:
        await update.message.reply_text("Returning to the main menu.", reply_markup=main_menu_keyboard())
        return MENU
    await update.message.reply_text("Please use the buttons provided.", reply_markup=ordering_keyboard())
    return ORDERING


async def checkout_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Legacy checkout path now redirects to the hosted catalogue flow."""
    await update.message.reply_text(
        miniapp_redirect_message(),
        reply_markup=catalogue_redirect_keyboard(),
    )
    return MENU


async def delivery_area(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect delivery area."""
    text = update.message.text.strip()
    if "Back to Menu" in text:
        await update.message.reply_text("Back to menu.", reply_markup=main_menu_keyboard())
        return MENU
    if text not in {"🌆 Metro Manila", "🌏 Outside Metro Manila"}:
        await update.message.reply_text("Please choose one option.", reply_markup=delivery_area_keyboard())
        return DELIVERY_AREA
    context.user_data["delivery_area"] = "Metro Manila" if text == "🌆 Metro Manila" else "Outside Metro Manila"
    if context.user_data["delivery_area"] == "Metro Manila":
        await update.message.reply_text(
            "Metro Manila: same‑day delivery (dispatch ~1 hour after payment & confirmation).\n"
            "No added bot fee. Lalamove shipping is paid directly to the rider."
        )
    else:
        await update.message.reply_text(
            "Outside Metro Manila: 3–5 days via J&T.\n"
            "Additional ₱100 will be added to your invoice."
        )
    sheets = await get_sheets(context)
    last = await asyncio.to_thread(sheets.get_last_delivery, update.effective_user.id)
    if last:
        context.user_data["last_delivery"] = last
        await update.message.reply_text(
            f"Use your last delivery info?\n\nName: {last['name']}\nAddress: {last['address']}\nContact: {last['contact']}",
            reply_markup=yes_no_keyboard(),
        )
        return DELIVERY_NAME
    await update.message.reply_text("What's the receiver name?", reply_markup=ReplyKeyboardRemove())
    return DELIVERY_NAME


async def delivery_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect delivery name (or reuse last)."""
    text = update.message.text.strip()
    last = context.user_data.get("last_delivery")
    if last and "yes" in text.lower():
        context.user_data.update(
            {
                "delivery_name": last["name"],
                "delivery_address": last["address"],
                "delivery_contact": last["contact"],
            }
        )
        await update.message.reply_text("Perfect. Applying your last details.")
        await send_checkout_preview(update, context)
        await update.message.reply_text("Pick your payment method. 💳", reply_markup=payment_keyboard())
        return PAYMENT_METHOD
    if last and "no" in text.lower():
        await update.message.reply_text("Alright. What's the receiver name?")
        context.user_data.pop("last_delivery", None)
        return DELIVERY_NAME

    if not last:
        context.user_data["delivery_name"] = text
        await update.message.reply_text("Please provide the complete delivery address.")
        return DELIVERY_ADDRESS

    await update.message.reply_text("Please answer Yes or No.", reply_markup=yes_no_keyboard())
    return DELIVERY_NAME


async def delivery_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect delivery address."""
    text = update.message.text.strip()
    context.user_data["delivery_address"] = text
    await update.message.reply_text("Contact number? 📱", reply_markup=ReplyKeyboardRemove())
    return DELIVERY_CONTACT


async def delivery_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect contact number."""
    text = update.message.text.strip()
    context.user_data["delivery_contact"] = text
    await send_checkout_preview(update, context)
    await update.message.reply_text("Pick your payment method. 💳", reply_markup=payment_keyboard())
    return PAYMENT_METHOD


async def promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Capture promo code and continue checkout with delivery area."""
    code = update.message.text.strip()
    context.user_data["promo_code"] = code
    await update.message.reply_text(
        "Where are we sending your order? 📍", reply_markup=delivery_area_keyboard()
    )
    return DELIVERY_AREA


async def payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect payment method and decide if proof is needed."""
    text = update.message.text.strip()
    if "Back to Menu" in text:
        await update.message.reply_text("Back to menu.", reply_markup=main_menu_keyboard())
        return MENU
    if not any(k in text for k in ["E-Wallet", "Bank Transfer", "Cash on Delivery"]):
        await update.message.reply_text("Pick a valid payment option.", reply_markup=payment_keyboard())
        return PAYMENT_METHOD
    if "E-Wallet" in text:
        context.user_data["payment_method"] = "E-Wallet"
    elif "Bank Transfer" in text:
        context.user_data["payment_method"] = "Bank Transfer"
    else:
        context.user_data["payment_method"] = "Cash on Delivery"
    await update.message.reply_text(payment_instructions(context.user_data["payment_method"]))
    if "Cash on Delivery" in text:
        return await finalize_order(update, context, proof_file_id="")
    await update.message.reply_text("Please upload your payment screenshot. 📸")
    return PAYMENT_PROOF


async def payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle payment proof photo upload."""
    document = update.message.document
    if document and str(document.mime_type or "").startswith("image/"):
        return await finalize_order(update, context, proof_file_id=document.file_id)
    if not update.message.photo:
        await update.message.reply_text("Please send a photo screenshot of payment. 📸")
        return PAYMENT_PROOF
    file_id = update.message.photo[-1].file_id
    return await finalize_order(update, context, proof_file_id=file_id)


async def finalize_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    proof_file_id: str,
) -> int:
    """Create order record, notify admins, and send invoice to user."""
    cart = context.user_data.get("cart", {})
    products_map: Dict[str, Product] = context.user_data.get("products", {})
    if not cart:
        await update.message.reply_text("Your cart is empty.")
        return ORDERING

    items = []
    subtotal = 0.0
    for sku, qty in cart.items():
        product = products_map.get(sku)
        if not product:
            continue
        line_total = product.price * qty
        subtotal += line_total
        items.append({"sku": sku, "name": product.name, "qty": qty, "line_total": line_total})

    if not items:
        await update.message.reply_text("No valid items in cart.")
        return ORDERING

    sheets = await get_sheets(context)
    ok, stock_err = await asyncio.to_thread(sheets.reserve_stock, items)
    if not ok:
        await update.message.reply_text(f"Stock check failed: {stock_err}\nPlease adjust your cart and try again.")
        return ORDERING
    area = context.user_data.get("delivery_area", "Metro Manila")
    payment_method = context.user_data.get("payment_method", "")
    discount_meta = await calculate_discount_breakdown(
        context,
        update.effective_user.id,
        context.user_data.get("promo_code", ""),
        subtotal,
    )
    discount = discount_meta["discount"]
    discount, shipping, total = compute_totals(subtotal, discount, area, payment_method)

    # Basic COD risk: too many cancelled COD orders puts new order on hold.
    status = "Pending Confirmation"
    if payment_method != "Cash on Delivery":
        status = "Awaiting Payment Verification"
    else:
        user_orders = await asyncio.to_thread(sheets.get_orders_by_user, update.effective_user.id)
        cod_cancels = sum(
            1
            for o in user_orders
            if str(o.get("payment_method", "")).strip().lower() == "cash on delivery"
            and str(o.get("status", "")).strip().lower() in {"cancelled", "canceled", "rejected"}
        )
        if cod_cancels >= COD_RISK_CANCEL_THRESHOLD:
            status = "COD Review Hold"

    user = update.effective_user
    order_id = f"DG{dt.datetime.utcnow().strftime('%y%m%d')}-{str(user.id)[-4:]}-{uuid.uuid4().hex[:4]}"
    order_data = {
        "order_id": order_id,
        "created_at": dt.datetime.utcnow().isoformat(),
        "user_id": user.id,
        "username": user.username or "",
        "full_name": user.full_name,
        "items": items,
        "subtotal": subtotal,
        "discount": discount,
        "promo_discount": discount_meta["promo_discount"],
        "reward_discount": discount_meta["reward_discount"],
        "reward_points_used": discount_meta["reward_points_used"],
        "shipping": shipping,
        "total": total,
        "delivery_name": context.user_data.get("delivery_name", ""),
        "delivery_address": context.user_data.get("delivery_address", ""),
        "delivery_contact": context.user_data.get("delivery_contact", ""),
        "delivery_area": area,
        "payment_method": payment_method,
        "payment_proof_file_id": proof_file_id,
        "status": status,
        "tracking_number": "",
    }

    stock_reserved = True
    points_redeemed = False
    try:
        current_points = discount_meta["loyalty_balance"]
        if discount_meta["reward_points_used"]:
            current_points = await asyncio.to_thread(
                sheets.redeem_loyalty_points, user.id, discount_meta["reward_points_used"], order_id
            )
            points_redeemed = True
        order_data["current_points"] = current_points

        await asyncio.to_thread(sheets.log_order, order_data)
        await asyncio.to_thread(
            sheets.log_audit,
            "order_created",
            user.id,
            "order",
            order_id,
            "{}",
            _safe_json(order_data),
            "new order",
        )
        await asyncio.to_thread(
            sheets.update_last_delivery,
            user.id,
            order_data["delivery_name"],
            order_data["delivery_address"],
            order_data["delivery_contact"],
            order_data["delivery_area"],
        )
    except Exception as exc:
        logger.exception("Failed to finalize order %s: %s", order_id, exc)
        if stock_reserved:
            try:
                await asyncio.to_thread(sheets.restore_stock, items)
            except Exception as restore_exc:
                logger.exception("Failed to restore stock for %s: %s", order_id, restore_exc)
        if points_redeemed:
            try:
                await asyncio.to_thread(sheets.restore_redeemed_loyalty_points, user.id, order_id)
            except Exception as restore_exc:
                logger.exception("Failed to restore loyalty points for %s: %s", order_id, restore_exc)
        await update.message.reply_text(
            "The order did not save completely because the sheet was temporarily unavailable. "
            "Please try checkout again in a moment."
        )
        return ORDERING

    invoice_text = build_invoice(order_data)
    await send_photo_or_text(
        update,
        context,
        ORDER_COMPLETE_IMAGE_PATH,
        invoice_text,
        parse_mode=ParseMode.MARKDOWN,
    )

    safe_name = html.escape(user.full_name or "")
    safe_username = html.escape(user.username or "no_username")
    safe_payment = html.escape(str(order_data["payment_method"]))
    packed_items = "\n".join(
        f"• {html.escape(str(item['name']))} x{int(item['qty'])} — ₱{float(item['line_total']):.2f}"
        for item in items
    )
    safe_delivery_name = html.escape(str(order_data["delivery_name"]))
    safe_delivery_contact = html.escape(str(order_data["delivery_contact"]))
    safe_delivery_address = html.escape(str(order_data["delivery_address"]))
    safe_delivery_area = html.escape(str(order_data["delivery_area"]))
    admin_text = (
        f"New order <b>{html.escape(order_id)}</b>\n"
        f"User: {safe_name} (@{safe_username})\n"
        f"Telegram ID: {user.id}\n"
        f"Total: ₱{total:.2f}\n"
        f"Payment: {safe_payment}\n\n"
        f"Discounts: promo ₱{order_data['promo_discount']:.2f}, loyalty ₱{order_data['reward_discount']:.2f}\n"
        f"Current Points: {int(float(order_data['current_points']))} pts\n\n"
        f"<b>Items To Pack</b>\n{packed_items}\n\n"
        f"<b>Delivery Details</b>\n"
        f"{safe_delivery_name} — {safe_delivery_contact}\n"
        f"{safe_delivery_address}\n"
        f"Area: {safe_delivery_area}\n\n"
        "Admin note: reply to this message in the admin group to message the customer."
    )
    if status == "Awaiting Payment Verification":
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Verify Payment", callback_data=f"payverify_approve:{order_id}"),
                    InlineKeyboardButton("❌ Reject Payment", callback_data=f"payverify_reject:{order_id}"),
                ]
            ]
        )
    else:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Confirm", callback_data=f"admin_confirm:{order_id}"),
                    InlineKeyboardButton("Reject", callback_data=f"admin_reject:{order_id}"),
                ],
                [InlineKeyboardButton("✅ Mark Delivered", callback_data=f"admin_delivered:{order_id}")],
            ]
        )
    sent_admin_notice = False
    try:
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=admin_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
        if proof_file_id:
            await context.bot.send_photo(
                chat_id=ADMIN_GROUP_ID,
                photo=proof_file_id,
                caption=f"Payment proof for order {order_id}",
            )
        sent_admin_notice = True
    except Exception as exc:
        logger.exception("Failed to notify admin group for %s: %s", order_id, exc)

    if not sent_admin_notice:
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
                if proof_file_id:
                    await context.bot.send_photo(
                        chat_id=admin_id,
                        photo=proof_file_id,
                        caption=f"Payment proof for order {order_id}",
                    )
            except Exception as exc:
                logger.warning("Failed to notify admin %s for %s: %s", admin_id, order_id, exc)

    context.user_data.pop("cart", None)
    context.user_data.pop("cart_message_id", None)
    context.user_data.pop("tracking_order_id", None)
    clear_abandoned_cart_reminder(context, user.id)
    await update.message.reply_text(
        "Order sent for confirmation. I'll update you soon. 💖\n\nWhile you wait, you can track your order anytime. 🔎",
        reply_markup=main_menu_keyboard(),
    )
    return MENU


async def admin_order_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin confirmation or rejection of an order."""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    if not is_admin(user.id):
        await query.message.reply_text("Admins only.")
        return

    action, order_id = query.data.split(":", 1)
    status = "Confirmed" if action == "admin_confirm" else "Rejected"
    sheets = await get_sheets(context)
    updated = await set_order_status_with_audit(
        context,
        order_id,
        status,
        "",
        actor_id=user.id,
        action="admin_order_action",
        notes=f"action={action}",
    )
    if updated:
        await query.message.reply_text(f"Order {order_id} marked as {status}.")
        order = await asyncio.to_thread(sheets.get_order_by_id, order_id)
        if order:
            user_id = int(order.get("user_id"))
            if status == "Confirmed":
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"Your order {order_id} is confirmed! 💖 We’ll update you with tracking soon.",
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"Your order {order_id} was rejected. Please contact support if needed.",
                )
    else:
        await query.message.reply_text("Order not found.")


async def payment_verify_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin payment verification callback."""
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest as exc:
        logger.warning("Failed to answer payment verification callback for %s: %s", query.data, exc)
    if not is_admin(query.from_user.id):
        await query.message.reply_text("Admins only.")
        return
    action, order_id = query.data.split(":", 1)
    status = "Confirmed" if action == "payverify_approve" else "Rejected"
    updated = await set_order_status_with_audit(
        context,
        order_id,
        status,
        "",
        actor_id=query.from_user.id,
        action="payment_verify",
        notes=action,
    )
    if not updated:
        await query.message.reply_text("Order not found.")
        return
    sheets = await get_sheets(context)
    order = await asyncio.to_thread(sheets.get_order_by_id, order_id)
    customer_notice = "Customer notification skipped: order is not linked to a Telegram ID."
    if order:
        user_id = parse_customer_chat_id(order)
        if user_id is not None:
            if status == "Confirmed":
                await context.bot.send_message(chat_id=user_id, text=f"Payment verified for {order_id}. Order confirmed. ✅")
            else:
                await context.bot.send_message(chat_id=user_id, text=f"Payment for {order_id} was rejected. Please contact support.")
            customer_notice = "Customer notified in Telegram."
    await query.message.reply_text(f"{order_id}: {status}\n{customer_notice}")


async def payment_queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: show payment verification queue."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    sheets = await get_sheets(context)
    orders = await asyncio.to_thread(sheets.get_all_orders)
    waiting = [
        o
        for o in orders
        if str(o.get("status", "")).strip().lower() == "awaiting payment verification"
    ]
    if not waiting:
        await update.message.reply_text("No orders in payment verification queue.")
        return
    waiting = sorted(waiting, key=lambda x: str(x.get("created_at", "")), reverse=True)
    for o in waiting[:30]:
        order_id = str(o.get("order_id", ""))
        text = (
            f"*Payment Queue*\n"
            f"Order: `{order_id}`\n"
            f"Name: {o.get('full_name', '-')}\n"
            f"Total: ₱{float(o.get('total') or 0):.2f}\n"
            f"Method: {o.get('payment_method', '-')}"
        )
        kb = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("✅ Verify Payment", callback_data=f"payverify_approve:{order_id}"),
                InlineKeyboardButton("❌ Reject Payment", callback_data=f"payverify_reject:{order_id}"),
            ]]
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def send_tracking_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: start interactive tracking flow."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    sheets = await get_sheets(context)
    orders_ws = await asyncio.to_thread(sheets._get_or_create_ws, "Orders", ORDER_HEADERS)
    orders = await asyncio.to_thread(sheets._safe_get_all_records, orders_ws, ORDER_HEADERS)
    pending = [
        o
        for o in orders
        if str(o.get("status", "")).strip().lower() in ["confirmed", "pending confirmation", "pending"]
        and not str(o.get("tracking_number", "")).strip()
    ]
    if not pending:
        await update.message.reply_text("No orders need tracking right now. ✅")
        return
    buttons = [
        [InlineKeyboardButton(f"{o.get('order_id')} - {o.get('full_name','')}", callback_data=f"tracksel:{o.get('order_id')}")]
        for o in pending
    ]
    await update.message.reply_text(
        "Select an order to attach tracking:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return TRACKING_SELECT


def _is_pending_order_status(status: str) -> bool:
    """Return True if status represents an unfinished order."""
    terminal = {"delivered", "received", "rejected", "cancelled", "canceled"}
    value = str(status or "").strip().lower()
    if not value:
        return True
    return value not in terminal


async def _get_pending_orders(context: ContextTypes.DEFAULT_TYPE) -> List[Dict[str, Any]]:
    """Load all non-terminal orders for admin viewing."""
    sheets = await get_sheets(context)
    orders_ws = await asyncio.to_thread(sheets._get_or_create_ws, "Orders", ORDER_HEADERS)
    orders = await asyncio.to_thread(sheets._safe_get_all_records, orders_ws, ORDER_HEADERS)
    return [o for o in orders if _is_pending_order_status(o.get("status", ""))]


async def _send_pending_orders_text(target, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send pending orders with action buttons."""
    if not is_admin(target.from_user.id):
        await target.message.reply_text("Admins only.")
        return
    pending = await _get_pending_orders(context)
    if not pending:
        await target.message.reply_text("No pending orders right now. ✅")
        return
    pending_sorted = sorted(pending, key=lambda x: str(x.get("created_at", "")), reverse=True)
    for o in pending_sorted:
        order_id = str(o.get("order_id", "-"))
        status_value = str(o.get("status") or "Pending")
        status_norm = status_value.strip().lower()
        is_payment_waiting = ("payment" in status_norm and "verification" in status_norm)
        text = "\n".join(
            [
                f"*Order:* `{order_id}`",
                f"*Name:* {o.get('full_name', '-')}",
                f"*Status:* {status_value}",
                f"*Tracking:* {o.get('tracking_number') or 'Pending'}",
                f"*Total:* ₱{float(o.get('total') or 0):.2f}",
            ]
        )
        rows = []
        if is_payment_waiting:
            rows.append(
                [
                    InlineKeyboardButton("✅ Confirm Payment", callback_data=f"adminpo:payapprove:{order_id}"),
                    InlineKeyboardButton("❌ Reject Payment", callback_data=f"adminpo:payreject:{order_id}"),
                ]
            )
        rows.extend(
            [
                [
                    InlineKeyboardButton("❌ Cancel", callback_data=f"adminpo:cancel:{order_id}"),
                    InlineKeyboardButton("⏸️ On Hold", callback_data=f"adminpo:hold:{order_id}"),
                ],
                [
                    InlineKeyboardButton("🔗 Send Tracking", callback_data=f"adminpo:track:{order_id}"),
                    InlineKeyboardButton("💬 Contact Customer", callback_data=f"adminpo:contact:{order_id}"),
                ],
                [
                    InlineKeyboardButton("✅ Confirm Delivery", callback_data=f"adminpo:delivered:{order_id}"),
                ],
            ]
        )
        keyboard = InlineKeyboardMarkup(rows)
        await target.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


async def pending_orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: show all pending orders."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    await _send_pending_orders_text(update, context)


async def send_tracking_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: /send_tracking_link ORDER_ID TRACKING_LINK"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    parts = update.message.text.split(maxsplit=2)
    if len(parts) < 3:
        await update.message.reply_text("Usage: /send_tracking_link ORDER_ID TRACKING_LINK")
        return
    order_id = parts[1].strip()
    link = parts[2].strip()
    sheets = await get_sheets(context)
    order = await asyncio.to_thread(sheets.get_order_by_id, order_id)
    if not order:
        await update.message.reply_text("Order not found.")
        return
    await set_order_status_with_audit(
        context, order_id, "Shipped", link, update.effective_user.id, "send_tracking_link_command"
    )
    user_id = parse_customer_chat_id(order)
    customer_notice = "Customer notification skipped: order is not linked to a Telegram ID."
    if user_id is not None:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Your order {order_id} is on the way! 🚚\nTracking: {link}",
        )
        customer_notice = "Customer notified in Telegram."
    await context.bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text=f"Tracking sent for {order_id}.",
    )
    await update.message.reply_text(f"Tracking link saved for {order_id}. ✅\n{customer_notice}")


async def admin_pending_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle pending-order action buttons."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.message.reply_text("Admins only.")
        return
    _, action, order_id = query.data.split(":", 2)
    sheets = await get_sheets(context)
    order = await asyncio.to_thread(sheets.get_order_by_id, order_id)
    if not order:
        await query.message.reply_text("Order not found.")
        return
    user_id = parse_customer_chat_id(order)
    missing_link_notice = "Customer notification skipped: order is not linked to a Telegram ID."

    if action == "cancel":
        await set_order_status_with_audit(
            context, order_id, "Cancelled", "", query.from_user.id, "pending_action_cancel"
        )
        if user_id is not None:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Your order {order_id} has been cancelled. Please contact support for help.",
            )
            await query.message.reply_text(f"Order {order_id} cancelled.\nCustomer notified in Telegram.")
        else:
            await query.message.reply_text(f"Order {order_id} cancelled.\n{missing_link_notice}")
        return

    if action == "hold":
        await set_order_status_with_audit(
            context, order_id, "On Hold", "", query.from_user.id, "pending_action_hold"
        )
        if user_id is not None:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Your order {order_id} is currently on hold. We will message you with an update soon.",
            )
            await query.message.reply_text(f"Order {order_id} placed on hold.\nCustomer notified in Telegram.")
        else:
            await query.message.reply_text(f"Order {order_id} placed on hold.\n{missing_link_notice}")
        return

    if action in {"payapprove", "payreject"}:
        new_status = "Confirmed" if action == "payapprove" else "Rejected"
        await set_order_status_with_audit(
            context, order_id, new_status, "", query.from_user.id, f"pending_action_{action}"
        )
        if user_id is not None and action == "payapprove":
            await context.bot.send_message(chat_id=user_id, text=f"Payment verified for {order_id}. Order confirmed. ✅")
        elif user_id is not None:
            await context.bot.send_message(chat_id=user_id, text=f"Payment for {order_id} was rejected. Please contact support.")
        if user_id is None:
            await query.message.reply_text(f"{order_id}: {new_status}\n{missing_link_notice}")
        else:
            await query.message.reply_text(f"{order_id}: {new_status}\nCustomer notified in Telegram.")
        return

    if action == "delivered":
        await set_order_status_with_audit(
            context, order_id, "Delivered", "", query.from_user.id, "pending_action_delivered"
        )
        if user_id is not None:
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("✅ I received it", callback_data=f"cust_received:{order_id}")]]
            )
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Your order {order_id} is marked as delivered. Please confirm receipt.",
                reply_markup=keyboard,
            )
            await query.message.reply_text(f"Order {order_id} marked as delivered.\nCustomer notified in Telegram.")
        else:
            await query.message.reply_text(f"Order {order_id} marked as delivered.\n{missing_link_notice}")
        return

    if action == "track":
        context.user_data["pending_action"] = {"type": "tracking_link", "order_id": order_id}
        await query.message.reply_text(
            f"Send the tracking link for order {order_id}.\nType `cancel` to abort.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if action == "contact":
        if user_id is None:
            await query.message.reply_text(f"Cannot contact customer for {order_id}: order is not linked to a Telegram ID.")
            return
        context.user_data["pending_action"] = {"type": "contact_customer", "order_id": order_id}
        await query.message.reply_text(
            f"Type your message for customer of order {order_id}.\nType `cancel` to abort.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return


async def admin_followup_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin freeform follow-up input for pending-order actions."""
    if not is_admin(update.effective_user.id):
        return
    pending_action = context.user_data.get("pending_action")
    if not pending_action:
        return
    text = update.message.text.strip()
    if text.lower() == "cancel":
        context.user_data.pop("pending_action", None)
        await update.message.reply_text("Action cancelled.")
        return

    action_type = pending_action.get("type")
    order_id = pending_action.get("order_id")
    sheets = await get_sheets(context)
    order = await asyncio.to_thread(sheets.get_order_by_id, order_id)
    if not order:
        context.user_data.pop("pending_action", None)
        await update.message.reply_text("Order not found.")
        return
    user_id = parse_customer_chat_id(order)

    if action_type == "tracking_link":
        link = text
        await set_order_status_with_audit(
            context, order_id, "Shipped", link, update.effective_user.id, "pending_tracking_link"
        )
        if user_id is not None:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Your order {order_id} is on the way! 🚚\nTracking: {link}",
            )
        await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=f"Tracking sent for {order_id}.")
        notice = "Customer notified in Telegram." if user_id is not None else "Customer notification skipped: order is not linked to a Telegram ID."
        await update.message.reply_text(f"Tracking link saved for {order_id}. ✅\n{notice}")
        context.user_data.pop("pending_action", None)
        return

    if action_type == "contact_customer":
        if user_id is None:
            await update.message.reply_text(f"Cannot contact customer for {order_id}: order is not linked to a Telegram ID.")
            context.user_data.pop("pending_action", None)
            return
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Message from support about order {order_id}:\n{text}",
        )
        await update.message.reply_text(f"Customer contacted for {order_id}. ✅")
        context.user_data.pop("pending_action", None)
        return


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for admin panel shortcuts."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📦 Show Pending Orders", callback_data="adminpanel:pending")],
            [InlineKeyboardButton("💳 Payment Queue", callback_data="adminpanel:payment_queue_help")],
            [InlineKeyboardButton("📊 Sales Dashboard", callback_data="adminpanel:sales_help")],
            [InlineKeyboardButton("📣 Broadcast Tools", callback_data="adminpanel:broadcast_help")],
            [InlineKeyboardButton("📤 Export Tools", callback_data="adminpanel:export_help")],
            [InlineKeyboardButton("🔗 Tracking Tools", callback_data="adminpanel:tracking_help")],
        ]
    )


async def admin_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin panel entrypoint."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    await update.message.reply_text(
        "Admin tools are now hosted in the Mini App dashboard.\n\nTap below to open them:",
        reply_markup=admin_tools_keyboard(),
    )


async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin panel button actions."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.message.reply_text("Admins only.")
        return
    action = query.data.split(":", 1)[1]
    if action == "pending":
        await _send_pending_orders_text(query, context)
        return
    if action == "tracking_help":
        await query.message.reply_text(
            "Tracking tools:\n"
            "`/send_tracking_link ORDER_ID TRACKING_LINK`\n\n"
            "`/send_tracking` (guided selection)",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if action == "payment_queue_help":
        await query.message.reply_text(
            "Payment tools:\n"
            "`/payment_queue` — orders awaiting payment verification",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if action == "sales_help":
        await query.message.reply_text(
            "Analytics:\n"
            "`/sales_dashboard` or `/sales_dashboard 30`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if action == "broadcast_help":
        await query.message.reply_text(
            "Broadcast tools:\n"
            "`/broadcast` — users broadcast with preview\n"
            "`/broadcast_groups MESSAGE`\n"
            "`/broadcast_channels MESSAGE`\n"
            "`/broadcast_group_members GROUP_ID MESSAGE`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if action == "export_help":
        await query.message.reply_text(
            "Export tools:\n"
            "`/export_users`\n"
            "`/export_groups`\n"
            "`/export_channels`\n"
            "`/export_group_members GROUP_ID`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return


async def broadcast_groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: manually broadcast a text message to all saved groups."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    message = update.message.text.partition(" ")[2].strip()
    if not message:
        await update.message.reply_text("Usage: /broadcast_groups your message here")
        return
    sheets = await get_sheets(context)
    groups = await asyncio.to_thread(sheets.list_groups)
    if not groups:
        await update.message.reply_text("No groups saved yet.")
        return
    sent = 0
    failed = 0
    for g in groups:
        chat_id = g.get("chat_id")
        if not chat_id:
            continue
        try:
            await context.bot.send_message(chat_id=int(chat_id), text=message)
            sent += 1
        except Exception as exc:
            logger.warning("Failed group broadcast to %s: %s", chat_id, exc)
            failed += 1
    await update.message.reply_text(f"Group broadcast complete. Sent: {sent}, Failed: {failed}")


async def broadcast_channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: manually broadcast a text message to all saved channels."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    message = update.message.text.partition(" ")[2].strip()
    if not message:
        await update.message.reply_text("Usage: /broadcast_channels your message here")
        return
    sheets = await get_sheets(context)
    channels = await asyncio.to_thread(sheets.list_channels)
    if not channels:
        await update.message.reply_text("No channels saved yet.")
        return
    sent = 0
    failed = 0
    for c in channels:
        chat_id = c.get("chat_id")
        if not chat_id:
            continue
        try:
            await context.bot.send_message(chat_id=int(chat_id), text=message)
            sent += 1
        except Exception as exc:
            logger.warning("Failed channel broadcast to %s: %s", chat_id, exc)
            failed += 1
    await update.message.reply_text(f"Channel broadcast complete. Sent: {sent}, Failed: {failed}")


async def _export_sheet_as_csv(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    sheet_name: str,
    headers: List[str],
    filename_prefix: str,
) -> None:
    """Export a worksheet as CSV and send it to admin."""
    sheets = await get_sheets(context)
    ws = await asyncio.to_thread(sheets._get_or_create_ws, sheet_name, headers)
    records = await asyncio.to_thread(sheets._safe_get_all_records, ws, headers)
    if not records:
        await update.message.reply_text(f"No data found in {sheet_name}.")
        return

    string_buffer = io.StringIO()
    writer = csv.DictWriter(string_buffer, fieldnames=headers)
    writer.writeheader()
    for row in records:
        writer.writerow({h: row.get(h, "") for h in headers})

    content = string_buffer.getvalue().encode("utf-8")
    bytes_buffer = io.BytesIO(content)
    bytes_buffer.seek(0)
    filename = f"{filename_prefix}_{dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    await update.message.reply_document(document=InputFile(bytes_buffer, filename=filename))


async def export_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: export Users sheet as CSV."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    headers = [
        "user_id",
        "username",
        "full_name",
        "last_delivery_name",
        "last_delivery_address",
        "last_delivery_contact",
        "last_delivery_area",
        "updated_at",
    ]
    await _export_sheet_as_csv(update, context, "Users", headers, "users_export")


async def export_groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: export Groups sheet as CSV."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    headers = ["chat_id", "title", "chat_type", "updated_at"]
    await _export_sheet_as_csv(update, context, "Groups", headers, "groups_export")


async def export_channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: export Channels sheet as CSV."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    headers = ["chat_id", "title", "updated_at"]
    await _export_sheet_as_csv(update, context, "Channels", headers, "channels_export")


def _resolve_group_id_from_command(update: Update, first_arg: str) -> Optional[int]:
    """Resolve group id from explicit arg or current group/supergroup chat."""
    if first_arg and first_arg.lstrip("-").isdigit():
        return int(first_arg)
    chat = update.effective_chat
    if chat and chat.type in {"group", "supergroup"}:
        return chat.id
    return None


async def broadcast_group_members_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: broadcast DM to known members of a specific group."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    payload = update.message.text.partition(" ")[2].strip()
    if not payload:
        await update.message.reply_text("Usage: /broadcast_group_members GROUP_ID message")
        return
    parts = payload.split(maxsplit=1)
    first_arg = parts[0]
    group_id = _resolve_group_id_from_command(update, first_arg)
    if group_id is None:
        await update.message.reply_text("Provide GROUP_ID or run this command inside the group.")
        return
    message = parts[1].strip() if first_arg.lstrip("-").isdigit() and len(parts) > 1 else payload
    if not message:
        await update.message.reply_text("Usage: /broadcast_group_members GROUP_ID message")
        return

    sheets = await get_sheets(context)
    members = await asyncio.to_thread(sheets.list_group_members, group_id)
    if not members:
        await update.message.reply_text("No captured group members yet for that group.")
        return

    seen: set[int] = set()
    sent = 0
    failed = 0
    for m in members:
        uid_raw = str(m.get("user_id", "")).strip()
        if not uid_raw or not uid_raw.lstrip("-").isdigit():
            continue
        uid = int(uid_raw)
        if uid in seen:
            continue
        seen.add(uid)
        try:
            await context.bot.send_message(chat_id=uid, text=message)
            sent += 1
        except Exception as exc:
            logger.warning("Failed member broadcast to %s: %s", uid, exc)
            failed += 1
    await update.message.reply_text(f"Member broadcast complete. Sent: {sent}, Failed: {failed}")


async def export_group_members_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: export known members of a group as CSV."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    arg = update.message.text.partition(" ")[2].strip()
    group_id = _resolve_group_id_from_command(update, arg)
    if group_id is None:
        await update.message.reply_text("Usage: /export_group_members GROUP_ID (or run in group)")
        return

    sheets = await get_sheets(context)
    headers = ["group_id", "group_title", "user_id", "username", "full_name", "status", "updated_at"]
    members = await asyncio.to_thread(sheets.list_group_members, group_id)
    if not members:
        await update.message.reply_text("No captured group members yet for that group.")
        return

    string_buffer = io.StringIO()
    writer = csv.DictWriter(string_buffer, fieldnames=headers)
    writer.writeheader()
    for row in members:
        writer.writerow({h: row.get(h, "") for h in headers})
    content = string_buffer.getvalue().encode("utf-8")
    bytes_buffer = io.BytesIO(content)
    bytes_buffer.seek(0)
    filename = f"group_members_{group_id}_{dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    await update.message.reply_document(document=InputFile(bytes_buffer, filename=filename))


async def customer_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Customer confirms receipt of order."""
    query = update.callback_query
    await query.answer()
    data = query.data
    order_id = data.split(":", 1)[1]
    sheets = await get_sheets(context)
    updated = await set_order_status_with_audit(
        context,
        order_id,
        "Received",
        "",
        actor_id=query.from_user.id,
        action="customer_received",
    )
    if updated:
        await query.message.reply_text("Thanks for confirming! 💖")
        order = await asyncio.to_thread(sheets.get_order_by_id, order_id)
        if order:
            balance, referral_awarded = await award_received_rewards(context, order)
            bonus_line = "\nReferral reward credited." if referral_awarded else ""
            await query.message.reply_text(f"Loyalty updated. Current balance: {balance} pts.{bonus_line}")
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=f"Order {order_id} marked as Received by customer.",
        )
    else:
        await query.message.reply_text("Order not found.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help text."""
    if is_admin(update.effective_user.id):
        text = (
            "Admin Help 🔧\n"
            "• /start — open the Mini App\n"
            "• /cancel — cancel current flow\n"
            "• /rewards — loyalty points and referral link\n\n"
            "Admin Controls\n"
            "• /admin — open the hosted admin dashboard\n"
            "• /setup — setup/repair sheets\n"
            "• /status — bot status"
        )
        await update.message.reply_text(text)
    else:
        text = (
            "Everything customer-facing now happens in the Mini App. 😈\n"
            "• Orders, tracking, rewards, and referrals are all handled there\n"
            "• For help or bulk orders, open the Mini App and use the chat support\n"
            "• Send /start anytime to get back to the main menu"
        )
        await update.message.reply_text(text, reply_markup=catalogue_redirect_keyboard())


async def payment_queue_alias(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await payment_queue_command(update, context)


async def sales_dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin KPI snapshot from orders."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    parts = update.message.text.split(maxsplit=1)
    days = 7
    if len(parts) == 2 and parts[1].isdigit():
        days = max(1, min(90, int(parts[1])))
    since = dt.datetime.utcnow() - dt.timedelta(days=days)
    sheets = await get_sheets(context)
    orders = await asyncio.to_thread(sheets.get_all_orders)
    filtered: List[Dict[str, Any]] = []
    for o in orders:
        created = str(o.get("created_at", ""))
        try:
            created_dt = dt.datetime.fromisoformat(created)
        except Exception:
            continue
        if created_dt < since:
            continue
        filtered.append(o)
    completed = [
        o
        for o in filtered
        if str(o.get("status", "")).strip().lower() not in {"rejected", "cancelled", "canceled"}
    ]
    revenue = sum(float(o.get("total", 0) or 0) for o in completed)
    count = len(completed)
    avg = revenue / count if count else 0.0
    cod = sum(1 for o in completed if str(o.get("payment_method", "")).strip().lower() == "cash on delivery")
    await update.message.reply_text(
        "\n".join(
            [
                f"*Sales Dashboard ({days}d)*",
                f"Orders (all): {len(filtered)}",
                f"Orders (counted): {count}",
                f"Revenue: ₱{revenue:.2f}",
                f"AOV: ₱{avg:.2f}",
                f"COD orders: {cod}",
            ]
        ),
        parse_mode=ParseMode.MARKDOWN,
    )


async def rewards_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show loyalty and referral details for current user."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            miniapp_redirect_message("rewards"),
            reply_markup=catalogue_redirect_keyboard(),
        )
        return
    sheets = await get_sheets(context)
    uid = update.effective_user.id
    balance = await asyncio.to_thread(sheets.get_loyalty_balance, uid)
    reward_points_used, reward_discount = compute_reward_redemption(balance, 10_000_000)
    referral_link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    await update.message.reply_text(
        "\n".join(
            [
                f"Your loyalty balance: {balance} pts 🎁",
                f"Your referral link: {referral_link}",
                f"Auto-redeem ready now: {reward_points_used} pts = ₱{reward_discount:.2f}",
                "",
                PROMO_TERMS_TEXT,
            ]
        ),
        reply_markup=referral_share_keyboard(uid),
    )


async def rollback_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin rollback last order status change from audit log."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    parts = update.message.text.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text("Usage: /rollback ORDER_ID")
        return
    order_id = parts[1].strip()
    sheets = await get_sheets(context)
    audits = await asyncio.to_thread(sheets.get_order_audit, order_id)
    if not audits:
        await update.message.reply_text("No audit history found for that order.")
        return
    last = audits[-1]
    try:
        before = json.loads(str(last.get("before_json", "{}")))
    except Exception:
        before = {}
    prev_status = str(before.get("status", "")).strip()
    prev_tracking = str(before.get("tracking_number", "")).strip()
    if not prev_status:
        await update.message.reply_text("Rollback not possible: previous status missing.")
        return
    ok = await set_order_status_with_audit(
        context,
        order_id,
        prev_status,
        prev_tracking,
        actor_id=update.effective_user.id,
        action="rollback",
        notes="manual rollback",
    )
    if ok:
        await update.message.reply_text(f"Rolled back {order_id} to status: {prev_status}")
    else:
        await update.message.reply_text("Rollback failed.")


async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: create or repair all sheet headers."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return

    sheets = await get_sheets(context)
    specs = {
        "Products": ["sku", "category", "name", "description", "price", "image_url", "active", "stock"],
        "Promos": ["code", "discount", "active"],
        "Users": [
            "user_id",
            "username",
            "full_name",
            "last_delivery_name",
            "last_delivery_address",
            "last_delivery_contact",
            "last_delivery_area",
            "updated_at",
        ],
        "Orders": [
            "order_id",
            "created_at",
            "user_id",
            "username",
            "full_name",
            "items_json",
            "subtotal",
            "discount",
            "shipping",
            "total",
            "delivery_name",
            "delivery_address",
            "delivery_contact",
            "delivery_area",
            "payment_method",
            "payment_proof_file_id",
            "status",
            "tracking_number",
        ],
        "Tickets": ["ticket_id", "created_at", "type", "user_id", "username", "message", "status"],
        "Affiliates": ["created_at", "user_id", "username", "twitter_or_telegram", "email", "contact", "subscriber_count"],
        "BroadcastLog": ["created_at", "admin_id", "message", "photo_file_id", "sent_count"],
        "Groups": ["chat_id", "title", "chat_type", "updated_at"],
        "Channels": ["chat_id", "title", "updated_at"],
        "GroupMembers": ["group_id", "group_title", "user_id", "username", "full_name", "status", "updated_at"],
        "AuditLog": ["created_at", "action", "actor_id", "target_type", "target_id", "before_json", "after_json", "notes"],
        "LoyaltyLedger": ["created_at", "user_id", "points_delta", "reason", "order_id"],
        "Referrals": ["user_id", "referrer_id", "created_at"],
        "PointsSummary": [
            "user_id",
            "current_points",
            "earned_points",
            "redeemed_points",
            "restored_points",
            "order_reward_count",
            "referral_reward_count",
            "updated_at",
        ],
        "ReferralSummary": [
            "referrer_id",
            "referred_user_id",
            "created_at",
            "status",
            "reward_points",
            "rewarded_at",
            "reward_order_id",
            "updated_at",
        ],
    }

    repaired = []
    repaired_order_rows = 0
    for title, headers in specs.items():
        ws = await asyncio.to_thread(sheets._get_or_create_ws, title, headers)
        # Write headers to row 1 to normalize
        await asyncio.to_thread(ws.update, "A1", [headers])
        repaired.append(title)
        if title == "Orders":
            repaired_order_rows = await asyncio.to_thread(sheets.repair_orders_sheet)
    await asyncio.to_thread(sheets.rebuild_rewards_summaries)

    await sync_bot_commands(context)
    await update.message.reply_text(
        f"Setup complete. Updated headers for: {', '.join(repaired)}\n"
        f"Orders rows normalized: {repaired_order_rows}\n"
        "Rewards summaries rebuilt: PointsSummary, ReferralSummary\n"
        "Bot commands synced: public commands are user-only; admin commands are scoped to admin accounts."
    )


async def sync_bot_commands(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sync command lists by scope: public default, admin-only for admin chat members."""
    await context.bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeDefault())
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.set_my_commands(
                ADMIN_COMMANDS,
                scope=BotCommandScopeChatMember(chat_id=admin_id, user_id=admin_id),
            )
        except Exception as exc:
            logger.warning("Failed to set admin command scope for %s: %s", admin_id, exc)


async def tracking_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle admin selecting an order for tracking."""
    query = update.callback_query
    await query.answer()
    data = query.data
    order_id = data.split(":", 1)[1]
    context.user_data["tracking_order_id"] = order_id
    await query.message.reply_text(
        f"Send the tracking link for order {order_id}:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return TRACKING_LINK


async def tracking_link_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive tracking link and send to customer."""
    link = update.message.text.strip()
    order_id = context.user_data.get("tracking_order_id")
    if not order_id:
        await update.message.reply_text("No order selected. Use /send_tracking again.")
        return ConversationHandler.END
    sheets = await get_sheets(context)
    order = await asyncio.to_thread(sheets.get_order_by_id, order_id)
    if not order:
        await update.message.reply_text("Order not found.")
        return ConversationHandler.END
    await set_order_status_with_audit(
        context, order_id, "Shipped", link, update.effective_user.id, "tracking_link_input"
    )
    user_id = int(order.get("user_id"))
    await context.bot.send_message(
        chat_id=user_id,
        text=f"Your order {order_id} is on the way! 🚚\nTracking: {link}",
    )
    delivered_keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Mark Delivered", callback_data=f"admin_delivered:{order_id}")]]
    )
    await context.bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text=f"Tracking sent for {order_id}. Mark delivered when completed.",
        reply_markup=delivered_keyboard,
    )
    await update.message.reply_text("Tracking sent to customer. ✅")
    context.user_data.pop("tracking_order_id", None)
    return ConversationHandler.END


async def admin_delivered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin marks order as delivered and asks customer to confirm receipt."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    order_id = query.data.split(":", 1)[1]
    sheets = await get_sheets(context)
    updated = await set_order_status_with_audit(
        context, order_id, "Delivered", "", query.from_user.id, "admin_delivered"
    )
    if not updated:
        await query.message.reply_text("Order not found.")
        return
    order = await asyncio.to_thread(sheets.get_order_by_id, order_id)
    if order:
        user_id = int(order.get("user_id"))
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ I received it", callback_data=f"cust_received:{order_id}")]]
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Your order {order_id} is marked as delivered. Please confirm receipt.",
            reply_markup=keyboard,
        )
        await schedule_post_purchase_followup(context, user_id, order_id)
    await query.message.reply_text(f"Order {order_id} marked as Delivered.")


async def received_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Customer manually confirms receipt: /received ORDER_ID."""
    parts = update.message.text.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text("Usage: /received ORDER_ID")
        return
    order_id = parts[1].strip()
    sheets = await get_sheets(context)
    updated = await set_order_status_with_audit(
        context, order_id, "Received", "", update.effective_user.id, "received_command"
    )
    if updated:
        await update.message.reply_text("Thanks for confirming! 💖")
        order = await asyncio.to_thread(sheets.get_order_by_id, order_id)
        if order:
            balance, referral_awarded = await award_received_rewards(context, order)
            bonus_line = "\nReferral reward credited." if referral_awarded else ""
            await update.message.reply_text(f"Loyalty updated. Current balance: {balance} pts.{bonus_line}")
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=f"Order {order_id} marked as Received by customer.",
        )
    else:
        await update.message.reply_text("Order not found.")


async def track_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle tracking choice."""
    text = update.message.text.strip()
    if "Back to Menu" in text:
        await update.message.reply_text("Back to menu.", reply_markup=main_menu_keyboard())
        return MENU
    if "By Order Number" in text:
        await update.message.reply_text("Send the order number. 🔢", reply_markup=ReplyKeyboardRemove())
        return TRACK_INPUT
    if "By My Telegram ID" in text:
        return await track_by_user(update, context)
    await update.message.reply_text("Pick a valid option.", reply_markup=track_keyboard())
    return TRACK_CHOICE


async def track_by_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Track by Telegram ID."""
    sheets = await get_sheets(context)
    orders = await asyncio.to_thread(sheets.get_orders_by_user, update.effective_user.id)
    if not orders:
        await update.message.reply_text(
            "I couldn't find any orders. Need admin help?",
            reply_markup=main_menu_keyboard(),
        )
        return MENU
    latest = orders[-1]
    await update.message.reply_text(
        f"Latest order: {latest.get('order_id')} 🧾\n"
        f"Status: {latest.get('status')}\n"
        f"Tracking: {latest.get('tracking_number') or 'Pending'}",
        reply_markup=main_menu_keyboard(),
    )
    return MENU


async def track_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle order number tracking."""
    order_id = update.message.text.strip()
    sheets = await get_sheets(context)
    order = await asyncio.to_thread(sheets.get_order_by_id, order_id)
    if not order:
        await update.message.reply_text(
            "I couldn't find that order. Need admin help?",
            reply_markup=main_menu_keyboard(),
        )
        return MENU
    await update.message.reply_text(
        f"Order {order_id} 🧾\nStatus: {order.get('status')}\nTracking: {order.get('tracking_number') or 'Pending'}",
        reply_markup=main_menu_keyboard(),
    )
    return MENU


async def customer_service_form(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect customer service message and notify admins."""
    message = update.message.text.strip()
    user = update.effective_user
    sheets = await get_sheets(context)
    ticket_id = await asyncio.to_thread(sheets.log_ticket, "customer_service", user.id, user.username or "", message)
    admin_text = (
        f"Customer support ticket *{ticket_id}*\n"
        f"User: {user.full_name} (@{user.username or 'no_username'})\n"
        f"User ID: {user.id}\n"
        f"Message: {message}\n\n"
        "Admin note: reply to this message in the admin group to respond to the customer."
    )
    await context.bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text=admin_text,
        parse_mode=ParseMode.MARKDOWN,
    )
    await update.message.reply_text(
        "Got it. The admin team has been notified and will reach out soon. 💬",
        reply_markup=main_menu_keyboard(),
    )
    return MENU


async def bulk_order_form(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect bulk order details and notify admins."""
    message = update.message.text.strip()
    user = update.effective_user
    sheets = await get_sheets(context)
    ticket_id = await asyncio.to_thread(sheets.log_ticket, "bulk_order", user.id, user.username or "", message)
    admin_text = (
        f"Bulk order ticket *{ticket_id}*\n"
        f"User: {user.full_name} (@{user.username or 'no_username'})\n"
        f"User ID: {user.id}\n"
        f"Message: {message}\n\n"
        "Admin note: reply to this message in the admin group to respond to the customer."
    )
    await context.bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text=admin_text,
        parse_mode=ParseMode.MARKDOWN,
    )
    await update.message.reply_text(
        "Thanks. We'll coordinate your bulk order ASAP. 📦",
        reply_markup=main_menu_keyboard(),
    )
    return MENU


async def affiliate_twitter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect affiliate handle."""
    context.user_data["affiliate_handle"] = update.message.text.strip()
    await update.message.reply_text("Email address? ✉️")
    return AFFILIATE_EMAIL


async def affiliate_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect affiliate email."""
    context.user_data["affiliate_email"] = update.message.text.strip()
    await update.message.reply_text("Contact number? 📱")
    return AFFILIATE_CONTACT


async def affiliate_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect affiliate contact."""
    context.user_data["affiliate_contact"] = update.message.text.strip()
    await update.message.reply_text("Subscriber count? 👥")
    return AFFILIATE_SUBS


async def affiliate_subs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect affiliate subscriber count and log."""
    context.user_data["affiliate_subs"] = update.message.text.strip()
    user = update.effective_user
    sheets = await get_sheets(context)
    await asyncio.to_thread(
        sheets.log_affiliate,
        {
            "user_id": user.id,
            "username": user.username or "",
            "handle": context.user_data.get("affiliate_handle", ""),
            "email": context.user_data.get("affiliate_email", ""),
            "contact": context.user_data.get("affiliate_contact", ""),
            "subs": context.user_data.get("affiliate_subs", ""),
        },
    )
    await context.bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text=(
            "New affiliate enrollment\n"
            f"User: {user.full_name} (@{user.username or 'no_username'})\n"
            f"Handle: {context.user_data.get('affiliate_handle', '')}\n"
            f"Email: {context.user_data.get('affiliate_email', '')}\n"
            f"Contact: {context.user_data.get('affiliate_contact', '')}\n"
            f"Subs: {context.user_data.get('affiliate_subs', '')}"
        ),
    )
    await update.message.reply_text(
        "You're in. We'll reach out with your affiliate details soon.",
        reply_markup=main_menu_keyboard(),
    )
    return MENU


async def custom_qty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom quantity input for a SKU."""
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("Please enter numbers only. 🔢")
        return CUSTOM_QTY
    qty = int(text)
    if qty <= 0:
        await update.message.reply_text("Quantity must be at least 1. 💖")
        return CUSTOM_QTY

    sku = context.user_data.get("qty_sku")
    if not sku:
        await update.message.reply_text("No item selected. Go back to the catalog. ↩️")
        return ORDERING

    products_map = context.user_data.get("products", {})
    product = products_map.get(sku)
    if product and qty > int(product.stock):
        await update.message.reply_text(f"Only {product.stock} left for this item.")
        return CUSTOM_QTY

    cart = context.user_data.setdefault("cart", {})
    cart[sku] = qty
    context.user_data.pop("qty_sku", None)
    await schedule_abandoned_cart_reminder(context, update.effective_chat.id, update.effective_user.id)
    await show_cart(context, update.effective_chat.id, cart, products_map)
    return ORDERING


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start admin broadcast flow."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return ConversationHandler.END
    await update.message.reply_text(
        "Send the broadcast message. You can attach a photo. 📣", reply_markup=ReplyKeyboardRemove()
    )
    return BROADCAST_MESSAGE


async def _perform_broadcast(
    context: ContextTypes.DEFAULT_TYPE,
    admin_id: int,
    message_text: str,
    photo_id: Optional[str],
) -> int:
    """Send broadcast to all users and log it."""
    sheets = await get_sheets(context)
    users_ws = await asyncio.to_thread(
        sheets._get_or_create_ws,
        "Users",
        [
            "user_id",
            "username",
            "full_name",
            "last_delivery_name",
            "last_delivery_address",
            "last_delivery_contact",
            "last_delivery_area",
            "updated_at",
        ],
    )
    users = sheets._safe_get_all_records(
        users_ws,
        [
            "user_id",
            "username",
            "full_name",
            "last_delivery_name",
            "last_delivery_address",
            "last_delivery_contact",
            "last_delivery_area",
            "updated_at",
        ],
    )
    order_now_button = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Order Now", url=f"https://t.me/{BOT_USERNAME}")]]
    )
    sent_count = 0
    for row in users:
        user_id = row.get("user_id")
        if not user_id:
            continue
        try:
            if photo_id:
                await context.bot.send_photo(
                    chat_id=int(user_id),
                    photo=photo_id,
                    caption=message_text,
                    reply_markup=order_now_button,
                )
            else:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=message_text,
                    reply_markup=order_now_button,
                )
            sent_count += 1
        except Exception as exc:
            logger.warning("Failed to broadcast to %s: %s", user_id, exc)

    await asyncio.to_thread(
        sheets.log_broadcast,
        {
            "admin_id": admin_id,
            "message": message_text,
            "photo_file_id": photo_id or "",
            "sent_count": sent_count,
        },
    )
    return sent_count


async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prepare a preview for broadcast."""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    message_text = update.message.caption or update.message.text or ""
    photo_id = None
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id

    context.user_data["broadcast_text"] = message_text
    context.user_data["broadcast_photo_id"] = photo_id

    preview_keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Send", callback_data="bcast_send"),
                InlineKeyboardButton("❌ Cancel", callback_data="bcast_cancel"),
            ]
        ]
    )

    if photo_id:
        await update.message.reply_photo(
            photo=photo_id,
            caption=f"Preview:\n\n{message_text}",
            reply_markup=preview_keyboard,
        )
    else:
        await update.message.reply_text(
            f"Preview:\n\n{message_text}",
            reply_markup=preview_keyboard,
        )
    return BROADCAST_PREVIEW


async def broadcast_preview_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle preview confirmation/cancel for broadcast."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    action = query.data
    if action == "bcast_cancel":
        context.user_data.pop("broadcast_text", None)
        context.user_data.pop("broadcast_photo_id", None)
        await query.message.reply_text("Broadcast cancelled.")
        return ConversationHandler.END

    message_text = context.user_data.get("broadcast_text", "")
    photo_id = context.user_data.get("broadcast_photo_id")
    sent_count = await _perform_broadcast(context, query.from_user.id, message_text, photo_id)
    context.user_data.pop("broadcast_text", None)
    context.user_data.pop("broadcast_photo_id", None)
    await query.message.reply_text(f"Broadcast sent to {sent_count} users.")
    return ConversationHandler.END


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin status command."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    await update.message.reply_text("Bot is running normally.")


async def update_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin order status update: /update_status ORDER_ID STATUS [TRACKING]."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    parts = update.message.text.split(maxsplit=3)
    if len(parts) < 3:
        await update.message.reply_text("Usage: /update_status ORDER_ID STATUS [TRACKING]")
        return
    order_id = parts[1]
    status = parts[2]
    tracking = parts[3] if len(parts) == 4 else ""
    sheets = await get_sheets(context)
    updated = await set_order_status_with_audit(
        context, order_id, status, tracking, update.effective_user.id, "update_status_command"
    )
    if updated:
        await update.message.reply_text(f"Order {order_id} updated.")
        if status.lower() in ["delivered", "received"]:
            order = await asyncio.to_thread(sheets.get_order_by_id, order_id)
            if order:
                user_id = int(order.get("user_id"))
                if status.lower() == "delivered":
                    keyboard = InlineKeyboardMarkup(
                        [[InlineKeyboardButton("✅ I received it", callback_data=f"cust_received:{order_id}")]]
                    )
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"Your order {order_id} is marked as delivered. Please confirm receipt.",
                        reply_markup=keyboard,
                    )
                    await schedule_post_purchase_followup(context, user_id, order_id)
                else:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"Order {order_id} marked as received. Thank you! 💖",
                    )
                    order = await asyncio.to_thread(sheets.get_order_by_id, order_id)
                    if order:
                        await award_received_rewards(context, order)
    else:
        await update.message.reply_text("Order not found.")


async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin reply to a user: /reply USER_ID message."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admins only.")
        return
    parts = update.message.text.split(maxsplit=2)
    if len(parts) < 3:
        await update.message.reply_text("Usage: /reply USER_ID message")
        return
    user_id = int(parts[1])
    message = parts[2]
    await context.bot.send_message(chat_id=user_id, text=f"Admin: {message}")
    await update.message.reply_text("Message sent.")


async def admin_group_reply_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Forward admin-group replies on bot notices back to the customer."""
    message = update.effective_message
    if not message or not update.effective_chat or update.effective_chat.id != ADMIN_GROUP_ID:
        return
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not message.reply_to_message or not message.text:
        return
    original = message.reply_to_message
    original_from = getattr(original, "from_user", None)
    if not original_from or original_from.id != context.bot.id:
        return

    target_user_id, reference = parse_forward_target_from_admin_message(original.text_html or original.text or "")
    if target_user_id is None:
        return

    outbound = message.text.strip()
    if not outbound:
        return

    prefix = f"Admin update for order {reference}:\n" if reference else "Admin update:\n"
    sent = await context.bot.send_message(
        chat_id=target_user_id,
        text=f"{prefix}{outbound}\n\nReply to this message to continue this thread.",
    )
    if reference:
        sheets = await get_sheets(context)
        await asyncio.to_thread(
            sheets.log_message_thread,
            {
                "message_id": str(uuid.uuid4()),
                "created_at": dt.datetime.utcnow().isoformat(),
                "order_id": reference,
                "ticket_id": "",
                "user_id": str(target_user_id),
                "username": "",
                "sender_type": "admin",
                "sender_name": message.from_user.full_name if message.from_user else "Admin",
                "message": outbound,
                "telegram_message_id": str(sent.message_id),
                "reply_to_message_id": str(getattr(original, "message_id", "") or ""),
                "read_by_admin": "true",
            },
        )
    await message.reply_text(f"Reply sent to customer {target_user_id}. ✅")


async def customer_thread_reply_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture customer replies to bot messages and append them into the order thread."""
    message = update.effective_message
    if not message or not update.effective_chat or update.effective_chat.type != "private":
        return
    if not update.effective_user or is_admin(update.effective_user.id):
        return
    original = getattr(message, "reply_to_message", None)
    if not original:
        return
    original_from = getattr(original, "from_user", None)
    if not original_from or original_from.id != context.bot.id:
        return

    reference = parse_thread_reference_from_bot_message(original.text or original.caption or "")
    if not reference:
        return

    body = extract_thread_message_text(message)
    if not body:
        return

    sheets = await get_sheets(context)
    username = update.effective_user.username or ""
    sender_name = update.effective_user.full_name or username or str(update.effective_user.id)
    await asyncio.to_thread(
        sheets.log_message_thread,
        {
            "message_id": str(uuid.uuid4()),
            "created_at": dt.datetime.utcnow().isoformat(),
            "order_id": reference,
            "ticket_id": "",
            "user_id": str(update.effective_user.id),
            "username": username,
            "sender_type": "customer",
            "sender_name": sender_name,
            "message": body,
            "telegram_message_id": str(message.message_id),
            "reply_to_message_id": str(getattr(original, "message_id", "") or ""),
            "read_by_admin": "false",
        },
    )

    adminText = [
        f"Customer reply for order {reference}",
        f"Customer: {sender_name}{f' (@{username})' if username else ''}",
        f"Telegram ID: {update.effective_user.id}",
        f"Telegram Username: @{username}" if username else "",
        "",
        body,
    ]
    await context.bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text="\n".join(line for line in adminText if line),
    )
    await message.reply_text("Your reply was sent to support. We’ll get back to you here.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel current flow."""
    if update.effective_user:
        clear_abandoned_cart_reminder(context, update.effective_user.id)
    await update.message.reply_text("Cancelled. Back to menu. ↩️", reply_markup=main_menu_keyboard())
    return MENU


def _bot_was_added(old_status: str, new_status: str) -> bool:
    """Return True when bot transitions from not-in-group to active group member/admin."""
    not_in_chat = {"left", "kicked"}
    in_chat = {"member", "administrator"}
    return old_status in not_in_chat and new_status in in_chat


def _member_joined(old_status: str, new_status: str) -> bool:
    """Return True when a user newly joins the chat."""
    not_in_chat = {"left", "kicked"}
    in_chat = {"member", "administrator", "restricted"}
    return old_status in not_in_chat and new_status in in_chat


NEW_MEMBER_WELCOME_TEXT = (
    "Welcome to Daddy Grab Super App.\n\n"
    "This group is powered by Daddy Grab, your one-stop shop for multiple product lines and customer services.\n\n"
    "For orders, updates, and support:\n"
    f"👉 t.me/{BOT_USERNAME}\n\n"
    "Everything you need is just one message away."
)
WELCOME_MESSAGES_ENABLED = False


async def _process_member_join(chat_id: int, user, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deduped welcome sender for member joins."""
    if not WELCOME_MESSAGES_ENABLED:
        return
    if user.id == context.bot.id:
        return
    cache = context.application.bot_data.setdefault("join_welcome_cache", {})
    key = f"{chat_id}:{user.id}"
    if cache.get(key):
        return
    try:
        await context.bot.send_message(chat_id=chat_id, text=NEW_MEMBER_WELCOME_TEXT)
        cache[key] = True
    except Exception as exc:
        logger.warning("Failed to send new-member welcome in %s for %s: %s", chat_id, user.id, exc)
        try:
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=f"Welcome send failed in {chat_id} for user {user.id}: {exc}",
            )
        except Exception:
            pass


async def on_bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle bot being added to groups/supergroups/channels and save target chat."""
    cmu = update.my_chat_member
    if not cmu:
        return
    chat = cmu.chat
    if chat.type not in {"group", "supergroup", "channel"}:
        return

    old_status = cmu.old_chat_member.status
    new_status = cmu.new_chat_member.status
    if not _bot_was_added(old_status, new_status):
        return

    sheets = await get_sheets(context)
    if chat.type == "channel":
        await asyncio.to_thread(sheets.upsert_channel, chat.id, chat.title or "")
    else:
        await asyncio.to_thread(sheets.upsert_group, chat.id, chat.title or "", chat.type)
    if chat.type == "supergroup":
        # Telegram Bot API does not provide full historical member list.
        # We seed with current admins, then continue collecting members from updates/activity.
        try:
            admins = await context.bot.get_chat_administrators(chat.id)
            for admin in admins:
                u = admin.user
                await asyncio.to_thread(
                    sheets.upsert_group_member,
                    chat.id,
                    chat.title or "",
                    u.id,
                    u.username or "",
                    u.full_name,
                    admin.status,
                )
        except Exception as exc:
            logger.warning("Failed to seed admins for group %s: %s", chat.id, exc)

    if WELCOME_MESSAGES_ENABLED and chat.type in {"group", "supergroup"}:
        group_name = html.escape(chat.title or "this group")
        caption = (
            f"Welcome to <b>{group_name}</b> 😌\n\n"
            "This group is powered by <b>Daddy Grab Super App</b>, your one-stop shop for multiple product lines and customer services.\n\n"
            "For orders and product support:\n"
            f"👉 <a href=\"https://t.me/{BOT_USERNAME}\">t.me/{BOT_USERNAME}</a>\n\n"
            "Everything you need is just one message away."
        )
        image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "welcome.jpg")
        try:
            with open(image_path, "rb") as photo:
                await context.bot.send_photo(
                    chat_id=chat.id,
                    photo=photo,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
        except Exception as exc:
            logger.warning("Failed to send group welcome image: %s", exc)
            await context.bot.send_message(chat_id=chat.id, text=caption, parse_mode=ParseMode.HTML)

    # Notify admin group for visibility.
    await context.bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text=(
            "Bot added to chat\n"
            f"Title: {chat.title or '-'}\n"
            f"Chat ID: {chat.id}\n"
            f"Type: {chat.type}\n"
            "Note: Telegram only allows bots to collect members progressively (no full historical list API)."
        ),
    )


async def on_group_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture member IDs from chat_member updates in groups/supergroups."""
    cmu = update.chat_member
    if not cmu:
        return
    chat = cmu.chat
    if chat.type not in {"group", "supergroup"}:
        return
    user = cmu.new_chat_member.user
    sheets = await get_sheets(context)
    await asyncio.to_thread(
        sheets.upsert_group_member,
        chat.id,
        chat.title or "",
        user.id,
        user.username or "",
        user.full_name,
        cmu.new_chat_member.status,
    )
    if _member_joined(cmu.old_chat_member.status, cmu.new_chat_member.status):
        await _process_member_join(chat.id, user, context)


async def on_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle service-message joins to ensure welcome broadcasts fire."""
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not chat or chat.type not in {"group", "supergroup"}:
        return
    new_members = msg.new_chat_members or []
    if not new_members:
        return
    sheets = await get_sheets(context)
    for user in new_members:
        if user.id == context.bot.id:
            continue
        await asyncio.to_thread(
            sheets.upsert_group_member,
            chat.id,
            chat.title or "",
            user.id,
            user.username or "",
            user.full_name,
            "member",
        )
        await _process_member_join(chat.id, user, context)


async def capture_group_message_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture sender IDs from regular messages in groups/supergroups."""
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not user:
        return
    if chat.type not in {"group", "supergroup"}:
        return
    key = (chat.id, user.id)
    now_ts = time.time()
    last_seen = context.application.bot_data.get("member_capture_last_seen", {})
    prev = last_seen.get(key, 0.0)
    if now_ts - prev < MEMBER_CAPTURE_THROTTLE_SECONDS:
        return
    last_seen[key] = now_ts
    context.application.bot_data["member_capture_last_seen"] = last_seen
    sheets = await get_sheets(context)
    await asyncio.to_thread(
        sheets.upsert_group_member,
        chat.id,
        chat.title or "",
        user.id,
        user.username or "",
        user.full_name,
        "active",
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler to keep visibility without killing polling loop."""
    logger.exception("Unhandled exception while processing update: %s", context.error)


async def on_startup(app: Application) -> None:
    """Notify admin group when bot process is live."""
    try:
        await app.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=f"{STORE_NAME} bot is now live. ✅",
        )
    except Exception as exc:
        logger.warning("Failed to send startup live notification: %s", exc)


def build_application() -> Application:
    """Build the Telegram application with all handlers."""
    PERSISTENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    persistence = JsonFilePersistence(filepath=str(PERSISTENCE_PATH))
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .persistence(persistence)
        .post_init(on_startup)
        .build()
    )

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("broadcast", broadcast_command),
            CommandHandler("send_tracking", send_tracking_command),
        ],
        name="daddygrab_main_conversation",
        persistent=True,
        allow_reentry=True,
        states={
            CONSENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, consent)],
            MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router)],
            ORDERING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ordering_router),
                CallbackQueryHandler(catalog_callback),
            ],
            DELIVERY_AREA: [MessageHandler(filters.TEXT & ~filters.COMMAND, delivery_area)],
            DELIVERY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, delivery_name)],
            DELIVERY_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, delivery_address)],
            DELIVERY_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, delivery_contact)],
            PROMO_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, promo_code)],
            PAYMENT_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_method)],
            PAYMENT_PROOF: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE | (filters.TEXT & ~filters.COMMAND), payment_proof)
            ],
            TRACK_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, track_choice)],
            TRACK_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, track_input)],
            CS_FORM: [MessageHandler(filters.TEXT & ~filters.COMMAND, customer_service_form)],
            BULK_FORM: [MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_order_form)],
            AFFILIATE_TWITTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, affiliate_twitter)],
            AFFILIATE_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, affiliate_email)],
            AFFILIATE_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, affiliate_contact)],
            AFFILIATE_SUBS: [MessageHandler(filters.TEXT & ~filters.COMMAND, affiliate_subs)],
            BROADCAST_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_message)],
            BROADCAST_PREVIEW: [CallbackQueryHandler(broadcast_preview_action, pattern=r"^bcast_")],
            CUSTOM_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_qty)],
            TRACKING_SELECT: [CallbackQueryHandler(tracking_select_callback, pattern=r"^tracksel:")],
            TRACKING_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, tracking_link_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & filters.REPLY
            & (filters.TEXT | filters.PHOTO | filters.Document.ALL)
            & ~filters.COMMAND,
            customer_thread_reply_router,
        ),
        group=-1,
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("setup", setup_command))
    app.add_handler(CommandHandler("received", received_command))
    app.add_handler(CommandHandler("update_status", update_status_command))
    app.add_handler(CommandHandler("reply", reply_command))
    app.add_handler(CommandHandler("payment_queue", payment_queue_alias))
    app.add_handler(CommandHandler("sales_dashboard", sales_dashboard_command))
    app.add_handler(CommandHandler("rewards", rewards_command))
    app.add_handler(CommandHandler("rollback", rollback_command))
    app.add_handler(CommandHandler("admin", admin_panel_command))
    app.add_handler(CommandHandler("pending_orders", pending_orders_command))
    app.add_handler(CommandHandler("send_tracking_link", send_tracking_link_command))
    app.add_handler(CommandHandler("broadcast_groups", broadcast_groups_command))
    app.add_handler(CommandHandler("broadcast_channels", broadcast_channels_command))
    app.add_handler(CommandHandler("broadcast_group_members", broadcast_group_members_command))
    app.add_handler(CommandHandler("export_users", export_users_command))
    app.add_handler(CommandHandler("export_groups", export_groups_command))
    app.add_handler(CommandHandler("export_channels", export_channels_command))
    app.add_handler(CommandHandler("export_group_members", export_group_members_command))
    app.add_handler(CallbackQueryHandler(admin_order_action, pattern=r"^admin_(confirm|reject):"))
    app.add_handler(CallbackQueryHandler(payment_verify_action, pattern=r"^payverify_(approve|reject):"))
    app.add_handler(CallbackQueryHandler(customer_received, pattern=r"^cust_received:"))
    app.add_handler(CallbackQueryHandler(admin_delivered, pattern=r"^admin_delivered:"))
    app.add_handler(MessageHandler(filters.Chat(chat_id=ADMIN_GROUP_ID) & filters.REPLY & filters.TEXT & ~filters.COMMAND, admin_group_reply_router))
    app.add_handler(CallbackQueryHandler(admin_panel_callback, pattern=r"^adminpanel:"))
    app.add_handler(CallbackQueryHandler(admin_pending_order_callback, pattern=r"^adminpo:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_followup_input))
    app.add_handler(ChatMemberHandler(on_bot_added_to_group, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(ChatMemberHandler(on_group_member_update, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_chat_members))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.ALL, capture_group_message_user))
    app.add_error_handler(on_error)

    return app


def main() -> None:
    """Start the bot."""
    try:
        with InstanceLock("daddygrab"):
            app = build_application()
            app.run_polling()
    except RuntimeError:
        logger.warning("Another Daddy Grab poller already owns the shared lock; exiting")


if __name__ == "__main__":
    main()
