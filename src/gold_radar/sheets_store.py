"""
طبقة تخزين البيانات في جداول جوجل (src/gold_radar/sheets_store.py).
لمشروع مرصاد الذهب (Gold Radar).

تتعامل مع ورقتين:
1. ورقة 'الحالة' (STATE_SHEET_NAME): لحفظ واسترجاع حالة التنبيهات (AlertState).
2. ورقة 'التاريخ' (HISTORY_SHEET_NAME): لحفظ سجل تاريخ الدورات والتنبيهات.

أمان صارم: إخفاء معرف الجدول ومفتاح حساب الخدمة وأي روابط أو أسرار من أي رسائل خطأ (raise ... from None).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import time
from typing import Any
import gspread
from google.oauth2.service_account import Credentials

from gold_radar.alert_logic import AlertState
from gold_radar.config import (
    HISTORY_SHEET_NAME,
    SHEETS_MAX_RETRIES,
    SHEETS_TIMEOUT_SECONDS,
    STATE_SHEET_NAME,
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# أعمدة ورقة التاريخ بالترتيب الصارم
HISTORY_COLUMNS = [
    "time",
    "ounce_usd",
    "usd_egp",
    "usd_source",
    "buy_24k",
    "sell_24k",
    "sell_21k",
    "sell_18k",
    "calculated_14k",
    "gold_pound_sell",
    "fair_24k",
    "gap_egp",
    "gap_pct",
    "status",
    "action",
    "change_pct",
]

# ترويسات ورقة التاريخ بالعربية مع توضيح اسم الحقل البرمجي
HISTORY_HEADERS = [
    "الوقت (time)",
    "أونصة الذهب (ounce_usd)",
    "سعر الدولار (usd_egp)",
    "مصدر الدولار (usd_source)",
    "شراء ع24 (buy_24k)",
    "بيع ع24 (sell_24k)",
    "بيع ع21 (sell_21k)",
    "بيع ع18 (sell_18k)",
    "ع14 المحسوب (calculated_14k)",
    "بيع الجنيه (gold_pound_sell)",
    "السعر العادل (fair_24k)",
    "الفجوة (gap_egp)",
    "نسبة الفجوة (gap_pct)",
    "حالة السوق (status)",
    "الإجراء (action)",
    "نسبة التغير (change_pct)",
]

STATE_HEADERS = ["المفتاح", "القيمة"]
STATE_KEYS = [
    "last_alert_price",
    "last_seen_price",
    "suspicious_count",
    "last_suspicious_price",
    "updated_at",
]


@dataclass
class SheetsHandle:
    """كائن المقبض لجداول جوجل يضم العميل والمصنف."""
    client: gspread.Client
    spreadsheet: gspread.Spreadsheet
    sheet_id: str


import re

def _clean_error(msg: str, secrets: list[str]) -> str:
    """تنظيف أي رسالة خطأ من الأسرار، معرف الجدول، أو روابط جداول جوجل."""
    cleaned = msg
    for s in secrets:
        if s and len(s) > 3:
            cleaned = cleaned.replace(s, "[REDACTED]")
    # إزالة أي روابط URL نهائياً لمنع ظهور رابط الجدول
    cleaned = re.sub(r"https?://[^\s'\"\)\]]+", "[REDACTED_URL]", cleaned)
    return cleaned


def open_store(service_account_json: str, sheet_id: str) -> SheetsHandle:
    """
    تهيئة الاتصال بجداول جوجل وفتح المصنف باستخدام بيانات حساب الخدمة.
    حماية كاملة للأسرار في حال حدوث أي خطأ.
    """
    clean_sheet_id = sheet_id.strip() if sheet_id else ""
    if not clean_sheet_id:
        raise ValueError("معرف جدول جوجل (GOOGLE_SHEET_ID) مفقود أو فارغ")

    if not service_account_json or not isinstance(service_account_json, str):
        raise ValueError("بيانات حساب الخدمة (GOOGLE_SERVICE_ACCOUNT_JSON) مفقودة أو غير صالحة")

    try:
        sa_info = json.loads(service_account_json)
    except Exception as exc:
        raise ValueError("فشل فك تشفير JSON لحساب خدمة جوجل (تنسيق غير صالح)") from None

    secrets_to_scrub = [clean_sheet_id, service_account_json]
    if isinstance(sa_info, dict):
        if "private_key" in sa_info:
            secrets_to_scrub.append(sa_info["private_key"])
        if "client_email" in sa_info:
            secrets_to_scrub.append(sa_info["client_email"])

    for attempt in range(1, SHEETS_MAX_RETRIES + 1):
        try:
            creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
            client = gspread.authorize(creds)
            # ضبط مهلة الانتظار لعميل gspread إذا أمكن
            if hasattr(client, "session") and hasattr(client.session, "timeout"):
                client.session.timeout = SHEETS_TIMEOUT_SECONDS

            spreadsheet = client.open_by_key(clean_sheet_id)
            return SheetsHandle(client=client, spreadsheet=spreadsheet, sheet_id=clean_sheet_id)
        except Exception as exc:
            if attempt < SHEETS_MAX_RETRIES:
                time.sleep(1.0 * attempt)
                continue
            err_msg = _clean_error(str(exc), secrets_to_scrub)
            raise RuntimeError(f"تعذر فتح جدول جوجل بعد {SHEETS_MAX_RETRIES} محاولات: {err_msg}") from None

    raise RuntimeError("فشل الاتصال بجداول جوجل") from None


def ensure_sheets(handle: SheetsHandle) -> None:
    """
    التأكد من وجود الورقتين ('الحالة' و 'التاريخ') بجدول جوجل وإنشائهما مع الترويسات إذا لم تكونا موجودتين.
    """
    sh = handle.spreadsheet
    secrets = [handle.sheet_id]

    try:
        existing_titles = [w.title for w in sh.worksheets()]
    except Exception as exc:
        raise RuntimeError(f"فشل قراءة أوراق الجدول: {_clean_error(str(exc), secrets)}") from None

    # 1. التأكد من ورقة الحالة (State Sheet)
    if STATE_SHEET_NAME not in existing_titles:
        try:
            ws_state = sh.add_worksheet(title=STATE_SHEET_NAME, rows=20, cols=5)
            initial_rows = [STATE_HEADERS] + [[k, ""] for k in STATE_KEYS]
            ws_state.update(initial_rows, "A1:B6")
        except Exception as exc:
            raise RuntimeError(f"فشل إنشاء ورقة '{STATE_SHEET_NAME}': {_clean_error(str(exc), secrets)}") from None

    # 2. التأكد من ورقة التاريخ (History Sheet)
    if HISTORY_SHEET_NAME not in existing_titles:
        try:
            ws_history = sh.add_worksheet(title=HISTORY_SHEET_NAME, rows=1000, cols=len(HISTORY_COLUMNS) + 2)
            ws_history.update([HISTORY_HEADERS], "A1")
        except Exception as exc:
            raise RuntimeError(f"فشل إنشاء ورقة '{HISTORY_SHEET_NAME}': {_clean_error(str(exc), secrets)}") from None


def read_state(handle: SheetsHandle) -> AlertState:
    """
    قراءة حالة التنبيهات من ورقة 'الحالة'.
    الخلايا الفارغة تعني None.
    إذا كانت الورقة فارغة بالكامل فقط يتم اعتبارها دورتنا الأولى.
    أي تلف أو نقص في المفاتيح يرفع خطأ صريحاً ولا يرجع حالة جديدة صامتاً.
    """
    sh = handle.spreadsheet
    secrets = [handle.sheet_id]

    try:
        ws = sh.worksheet(STATE_SHEET_NAME)
    except Exception as exc:
        raise RuntimeError(f"ورقة الحالة '{STATE_SHEET_NAME}' غير موجودة: {_clean_error(str(exc), secrets)}") from None

    try:
        rows = ws.get_all_values()
    except Exception as exc:
        raise RuntimeError(f"فشل قراءة بيانات ورقة الحالة: {_clean_error(str(exc), secrets)}") from None

    # إذا كانت الورقة خالية تماماً، أو تحتوي فقط على صف الترويسة وبلا بيانات
    if len(rows) == 0:
        return AlertState(last_alert_price=None, last_seen_price=None, suspicious_count=0, last_suspicious_price=None)

    # التحقق من وجود الترويسة أو الصفوف
    first_row = [c.strip() for c in rows[0]]
    if len(rows) == 1 and first_row == STATE_HEADERS:
        # ورقة جديدة وفارغة حقاً بعد الترويسة
        return AlertState(last_alert_price=None, last_seen_price=None, suspicious_count=0, last_suspicious_price=None)

    # تحويل البيانات إلى قاموس {مفتاح: قيمة}
    data_map: dict[str, str] = {}
    for r in rows:
        if len(r) >= 1 and r[0].strip() and r[0].strip() != "المفتاح":
            val = r[1].strip() if len(r) > 1 else ""
            data_map[r[0].strip()] = val

    # إذا كانت الورقة تحتوي على الترويسة لكن كافة المفاتيح مفقودة
    if not data_map and first_row == STATE_HEADERS:
        return AlertState(last_alert_price=None, last_seen_price=None, suspicious_count=0, last_suspicious_price=None)

    # فحص المفاتيح المطلوبة بدقة: إذا فقد أحدها يعتبر الجدول تالفاً ولا نرجع حالة فارغة
    required_keys = ["last_alert_price", "last_seen_price", "suspicious_count", "last_suspicious_price"]
    missing = [k for k in required_keys if k not in data_map]
    if missing:
        raise RuntimeError(f"ورقة الحالة تالفة أو ينقصها مفاتيح أساسية: {missing}")

    def _parse_optional_float(val: str, field_name: str) -> float | None:
        if not val or val.lower() == "none":
            return None
        try:
            return float(val)
        except ValueError:
            raise RuntimeError(f"قيمة غير صالحة للحقل '{field_name}' في جدول الحالة: {val!r}")

    def _parse_int(val: str, field_name: str, default: int = 0) -> int:
        if not val or val.lower() == "none":
            return default
        try:
            return int(float(val))
        except ValueError:
            raise RuntimeError(f"قيمة غير صالحة للحقل '{field_name}' في جدول الحالة: {val!r}")

    last_alert = _parse_optional_float(data_map["last_alert_price"], "last_alert_price")
    last_seen = _parse_optional_float(data_map["last_seen_price"], "last_seen_price")
    suspicious_count = _parse_int(data_map["suspicious_count"], "suspicious_count", default=0)
    last_suspicious = _parse_optional_float(data_map["last_suspicious_price"], "last_suspicious_price")

    return AlertState(
        last_alert_price=last_alert,
        last_seen_price=last_seen,
        suspicious_count=suspicious_count,
        last_suspicious_price=last_suspicious,
    )


def write_state(handle: SheetsHandle, state: AlertState) -> None:
    """
    كتابة وتحديث حالة التنبيهات في ورقة 'الحالة'.
    """
    sh = handle.spreadsheet
    secrets = [handle.sheet_id]

    try:
        ws = sh.worksheet(STATE_SHEET_NAME)
    except Exception as exc:
        raise RuntimeError(f"تعذر العثور على ورقة الحالة للكتابة: {_clean_error(str(exc), secrets)}") from None

    update_rows = [
        STATE_HEADERS,
        ["last_alert_price", str(state.last_alert_price) if state.last_alert_price is not None else ""],
        ["last_seen_price", str(state.last_seen_price) if state.last_seen_price is not None else ""],
        ["suspicious_count", str(state.suspicious_count)],
        ["last_suspicious_price", str(state.last_suspicious_price) if state.last_suspicious_price is not None else ""],
        ["updated_at", datetime.now(timezone.utc).isoformat()],
    ]

    for attempt in range(1, SHEETS_MAX_RETRIES + 1):
        try:
            ws.update(update_rows, "A1:B6")
            return
        except Exception as exc:
            if attempt < SHEETS_MAX_RETRIES:
                time.sleep(1.0 * attempt)
                continue
            raise RuntimeError(f"فشل كتابة الحالة في جدول جوجل: {_clean_error(str(exc), secrets)}") from None


def append_history(handle: SheetsHandle, row: dict[str, Any]) -> None:
    """
    إضافة صف جديد إلى ورقة 'التاريخ' بالترتيب الصارم للأعمدة.
    """
    sh = handle.spreadsheet
    secrets = [handle.sheet_id]

    try:
        ws = sh.worksheet(HISTORY_SHEET_NAME)
    except Exception as exc:
        raise RuntimeError(f"تعذر العثور على ورقة التاريخ: {_clean_error(str(exc), secrets)}") from None

    # استخراج القيم وفق الترتيب الصارم لـ HISTORY_COLUMNS
    ordered_values = []
    for col in HISTORY_COLUMNS:
        val = row.get(col, "")
        if val is None:
            ordered_values.append("")
        else:
            ordered_values.append(val)

    for attempt in range(1, SHEETS_MAX_RETRIES + 1):
        try:
            ws.append_row(ordered_values, value_input_option="USER_ENTERED")
            return
        except Exception as exc:
            if attempt < SHEETS_MAX_RETRIES:
                time.sleep(1.0 * attempt)
                continue
            raise RuntimeError(f"فشل إضافة صف في ورقة التاريخ: {_clean_error(str(exc), secrets)}") from None
