"""
المصدر الاحتياطي لسعر صرف الدولار (src/gold_radar/sources/usd_er_api.py).
يجلب السعر من Open Exchange Rates API (https://open.er-api.com/v6/latest/USD).

تنبيه قانوني (Attribution Requirement):
وفقاً لشروط استخدام ExchangeRate-API المجانية، يتطلب استخدام بيانات هذا المصدر
في الرسائل الموجهة للمستخدمين ذكر الإسناد ورابط المصدر (Attribution to exchangerate-api.com).
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from gold_radar.config import MAX_USD_AGE_DAYS, USD_EGP_MAX, USD_EGP_MIN
from gold_radar.sources.http import http_get
from gold_radar.sources.models import UsdRate

ER_API_URL = "https://open.er-api.com/v6/latest/USD"


def parse_usd_er_api_response(data: dict, now: datetime | None = None) -> UsdRate:
    """
    تحليل بيانات JSON لمصدر open.er-api والتحقق من قيمة EGP وتوقيت التحديث.
    دالة نقية تقبل وقت 'now' لتسهيل اختبارات الوحدة.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if not isinstance(data, dict):
        raise ValueError("تنسيق استجابة open.er-api غير صالح، المتوقع كائن JSON (dict)")

    if data.get("result") != "success":
        raise ValueError(f"استجابة open.er-api تفيد بعدم النجاح: {data.get('result')}")

    rates = data.get("rates")
    if not isinstance(rates, dict):
        raise ValueError("حقل 'rates' مفقود في استجابة open.er-api")

    raw_rate = rates.get("EGP")
    if raw_rate is None or isinstance(raw_rate, bool) or not isinstance(raw_rate, (int, float)):
        raise ValueError(f"قيمة سعر صرف الدولار مقابل الجنيه (EGP) مفقودة أو غير صالحة: {raw_rate!r}")

    rate = float(raw_rate)
    if not (USD_EGP_MIN <= rate <= USD_EGP_MAX):
        raise ValueError(
            f"سعر صرف الدولار من open.er-api ({rate} ج.م) خارج النطاق المنطقي المسموح [{USD_EGP_MIN}, {USD_EGP_MAX}]"
        )

    # التحقق من توقيت التحديث
    time_str = data.get("time_last_update_utc")
    if not time_str or not isinstance(time_str, str):
        raise ValueError("حقل وقت التحديث 'time_last_update_utc' مفقود في استجابة open.er-api")

    try:
        updated_at = parsedate_to_datetime(time_str)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
    except Exception as exc:
        raise ValueError(f"فشل تحليل صيغة وقت open.er-api '{time_str}': {exc}") from exc

    age_seconds = (now - updated_at).total_seconds()
    max_age_seconds = MAX_USD_AGE_DAYS * 86400.0

    if age_seconds > max_age_seconds:
        raise ValueError(
            f"بيانات open.er-api قديمة ({age_seconds / 86400.0:.1f} يوم مضت)، "
            f"وتتجاوز الحد المسموح ({MAX_USD_AGE_DAYS} يوم)"
        )
    if age_seconds < -300.0:
        raise ValueError(f"توقيت تحديث open.er-api يقع في المستقبل: {time_str}")

    return UsdRate(rate=rate, source_name="open.er-api.com", fetched_at=now)


def fetch_usd_er_api() -> UsdRate:
    """جلب سعر صرف الدولار من المصدر الاحتياطي (open.er-api.com)."""
    response = http_get(ER_API_URL)
    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError(f"فشل فك تشفير JSON من open.er-api: {exc}") from exc

    return parse_usd_er_api_response(data)
