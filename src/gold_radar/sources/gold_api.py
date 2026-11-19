"""
مصدر سعر أونصة الذهب العالمي (src/gold_radar/sources/gold_api.py).
يجلب السعر من Gold-API (https://api.gold-api.com/price/XAU)
ويتحقق من وجود طابع زمني دقيق بصيغة ISO وعدم تجاوز البيانات لعمر أقصاه 30 دقيقة.
"""

from datetime import datetime, timezone
from gold_radar.config import (
    MAX_OUNCE_AGE_MINUTES,
    OUNCE_USD_MAX,
    OUNCE_USD_MIN,
)
from gold_radar.sources.http import http_get
from gold_radar.sources.models import OuncePrice

GOLD_API_URL = "https://api.gold-api.com/price/XAU"


def parse_gold_api_response(data: dict, now: datetime | None = None) -> OuncePrice:
    """
    تحليل بيانات JSON الواردة من Gold-API والتحقق من صحتها ومن حداثة الطابع الزمني.
    دالة نقية تقبل وقت 'now' لتسهيل اختبارات الوحدة.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if not isinstance(data, dict):
        raise ValueError("تنسيق بيانات Gold-API غير صالح، المتوقع كائن JSON (dict)")

    raw_price = data.get("price")
    if raw_price is None or isinstance(raw_price, bool) or not isinstance(raw_price, (int, float)):
        raise ValueError(f"قيمة سعر أونصة الذهب غير صالحة أو مفقودة: {raw_price!r}")

    price = float(raw_price)
    if not (OUNCE_USD_MIN <= price <= OUNCE_USD_MAX):
        raise ValueError(
            f"سعر أونصة الذهب ({price} USD) خارج النطاق المنطقي المسموح [{OUNCE_USD_MIN}, {OUNCE_USD_MAX}]"
        )

    # التحقق من وجود الطابع الزمني المقروء آلياً
    raw_timestamp = data.get("updatedAt")
    if not raw_timestamp or not isinstance(raw_timestamp, str):
        # التحقق مما إذا كان يتوفر فقط النص النسبي
        if data.get("updatedAtReadable"):
            raise ValueError(
                "بيانات Gold-API تحتوي فقط على نص وصفي نسبي (updatedAtReadable) دون طابع زمني دقيق مقروء آلياً (updatedAt)"
            )
        raise ValueError("بيانات Gold-API لا تحتوي على طابع زمني للتحديث (updatedAt)")

    try:
        # تحويل صيغة ISO 8601 (مثل 2026-11-18T18:58:01Z)
        iso_str = raw_timestamp.replace("Z", "+00:00")
        updated_at = datetime.fromisoformat(iso_str)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
    except Exception as exc:
        raise ValueError(f"فشل تحليل الطابع الزمني للذهب '{raw_timestamp}': {exc}") from exc

    # التحقق من عمر البيانات
    age_seconds = (now - updated_at).total_seconds()
    max_age_seconds = MAX_OUNCE_AGE_MINUTES * 60.0

    if age_seconds > max_age_seconds:
        raise ValueError(
            f"بيانات أونصة الذهب قديمة جداً ({age_seconds / 60.0:.1f} دقيقة مضت)، "
            f"وتتجاوز الحد الأقصى المسموح ({MAX_OUNCE_AGE_MINUTES} دقيقة)"
        )

    # فحص الأمان من الطوابع الزمنية المستقبلية الشاذة (أكثر من 5 دقائق في المستقبل)
    if age_seconds < -300.0:
        raise ValueError(f"الطابع الزمني للأونصة يقع في المستقبل بشكل غير منطقي: {raw_timestamp}")

    return OuncePrice(usd=price, fetched_at=now)


def fetch_ounce_price() -> OuncePrice:
    """جلب سعر الأونصة بالدولار لحظياً من Gold-API."""
    response = http_get(GOLD_API_URL)
    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError(f"فشل فك تشفير JSON من Gold-API: {exc}") from exc

    return parse_gold_api_response(data)
