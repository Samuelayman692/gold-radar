"""
بناء وتنسيق رسائل التنبيه (src/gold_radar/message.py).
لمشروع مرصاد الذهب (Gold Radar).

دالة نقية (pure function) تماماً بدون أي اتصال شبكي أو قراءة/كتابة ملفات،
تنسق البيانات الرقمية المجمعة في نص رسالة واضحة وأنيقة بدون Markdown أو HTML.
"""

from dataclasses import dataclass
from datetime import datetime
import math
from zoneinfo import ZoneInfo

from gold_radar.config import CALCULATED_TAG, MESSAGE_TIMEZONE, USD_LABEL

STATUS_MAP_AR = {
    "higher": "أعلى",
    "lower": "أقل",
    "balanced": "متوازن",
}


@dataclass(frozen=True)
class MessageData:
    """كائن بيانات الرسالة المجهزة للعرض."""
    price_24k: float
    price_21k: float
    price_18k: float
    price_14k: float
    gold_pound: float
    ounce_usd: float
    usd_egp: float
    fair_24k: float
    gap_egp: float
    gap_pct: float
    status: str
    updated_at_utc: datetime


def _validate_positive_price(name: str, val: float | int) -> float:
    """التحقق من أن قيمة السعر رقم موجب وصالح وغير فارغ ولا يساوي NaN."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ValueError(f"قيمة '{name}' يجب أن تكون رقماً صالحاً، المعطى: {val!r}")
    if math.isnan(val) or math.isinf(val) or val <= 0.0:
        raise ValueError(f"قيمة '{name}' غير صالحة أو صفرية أو سالبة: {val}")
    return float(val)


def _validate_numeric(name: str, val: float | int) -> float:
    """التحقق من أن القيمة رقمية وصالحة (يمكن أن تكون سالبة أو موجبة)."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ValueError(f"قيمة '{name}' يجب أن تكون رقماً صالحاً، المعطى: {val!r}")
    if math.isnan(val) or math.isinf(val):
        raise ValueError(f"قيمة '{name}' غير صالحة (NaN أو ما لا نهاية): {val}")
    return float(val)


def build_message(data: MessageData) -> str:
    """
    بناء وتنسيق نص رسالة تيليجرام وفق التخطيط المحدد بدقة:
    - فواصل الآلاف بفاصلة وعشريين لجميع الأسعار.
    - إشارة صريحة (+ أو -) للفجوة ونسبتها.
    - تحويل التوقيت إلى توقيت القاهرة.
    - وسم (محسوب) فقط لعيار 14.
    """
    if not isinstance(data, MessageData):
        raise ValueError("المدخلات يجب أن تكون كائناً من نوع MessageData")

    # التحقق من الأسعار الإيجابية
    p24 = _validate_positive_price("price_24k", data.price_24k)
    p21 = _validate_positive_price("price_21k", data.price_21k)
    p18 = _validate_positive_price("price_18k", data.price_18k)
    p14 = _validate_positive_price("price_14k", data.price_14k)
    pound = _validate_positive_price("gold_pound", data.gold_pound)
    ounce = _validate_positive_price("ounce_usd", data.ounce_usd)
    usd = _validate_positive_price("usd_egp", data.usd_egp)
    fair = _validate_positive_price("fair_24k", data.fair_24k)

    # التحقق من الفجوة وحالة السوق
    gap_val = _validate_numeric("gap_egp", data.gap_egp)
    gap_percent = _validate_numeric("gap_pct", data.gap_pct)

    if data.status not in STATUS_MAP_AR:
        raise ValueError(f"حالة السوق غير معروفة '{data.status}'، الحالات المقبولة: {list(STATUS_MAP_AR.keys())}")
    status_ar = STATUS_MAP_AR[data.status]

    # التحقق من التوقيت والتحويل لتوقيت القاهرة
    if not isinstance(data.updated_at_utc, datetime):
        raise ValueError("updated_at_utc يجب أن يكون كائن datetime")
    if data.updated_at_utc.tzinfo is None:
        raise ValueError("updated_at_utc يجب أن يحتوي على منطقة زمنية واعية (aware datetime)")

    cairo_tz = ZoneInfo(MESSAGE_TIMEZONE)
    local_time = data.updated_at_utc.astimezone(cairo_tz)
    time_str = local_time.strftime("%Y-%m-%d %H:%M")

    # تجميع أسطر الرسالة بالتخطيط الصارم المطلوب
    lines = [
        "🟡 مرصاد الذهب",
        f"💰 السعر المحلي ع24 : {p24:,.2f} ج.م",
        f"💰 السعر المحلي ع21 : {p21:,.2f} ج.م",
        f"💰 السعر المحلي ع18 : {p18:,.2f} ج.م",
        f"💰 السعر المحلي ع14 : {p14:,.2f} ج.م ({CALCULATED_TAG})",
        f"🪙 الجنيه الذهب : {pound:,.2f} ج.م",
        f"🌍 الأونصة عالمياً : ${ounce:,.2f}",
        f"💵 {USD_LABEL} : {usd:,.2f} ج.م",
        f"⚖️ السعر العادل ع24 : {fair:,.2f} ج.م",
        f"📈 الفجوة السعرية : {gap_val:+,.2f} ج.م ({gap_percent:+.2f}%)",
        f"📊 حالة السوق : {status_ar}",
        f"🕐 آخر تحديث : {time_str}",
        "مؤشر للمتابعة وليس نصيحة استثمارية.",
    ]

    return "\n".join(lines)
