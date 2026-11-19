"""
المصدر الأساسي لسعر صرف الدولار (src/gold_radar/sources/usd_fawaz.py).
يجلب السعر من Fawaz Ahmed Currency API عبر شبكة jsDelivr العالمية:
https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json
ويتحقق من تاريخ البيانات ويرفضها إذا زاد عمرها عن يومين.
"""

from datetime import datetime, timezone
from gold_radar.config import MAX_USD_AGE_DAYS, USD_EGP_MAX, USD_EGP_MIN
from gold_radar.sources.http import http_get
from gold_radar.sources.models import UsdRate

FAWAZ_USD_URL = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json"


def parse_usd_fawaz_response(data: dict, now: datetime | None = None) -> UsdRate:
    """
    تحليل بيانات JSON لمصدر Fawaz والتحقق من قيمة EGP وتاريخ التحديث.
    دالة نقية تقبل وقت 'now' لتسهيل اختبارات الوحدة.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if not isinstance(data, dict):
        raise ValueError("تنسيق استجابة Fawaz Currency API غير صالح، المتوقع كائن JSON (dict)")

    usd_data = data.get("usd")
    if not isinstance(usd_data, dict):
        raise ValueError("حقل 'usd' مفقود أو غير صالح في استجابة Fawaz Currency API")

    raw_rate = usd_data.get("egp")
    if raw_rate is None or isinstance(raw_rate, bool) or not isinstance(raw_rate, (int, float)):
        raise ValueError(f"قيمة صرف الدولار مقابل الجنيه (EGP) مفقودة أو غير رقمية: {raw_rate!r}")

    rate = float(raw_rate)
    if not (USD_EGP_MIN <= rate <= USD_EGP_MAX):
        raise ValueError(
            f"سعر صرف الدولار ({rate} ج.م) خارج النطاق المنطقي المسموح [{USD_EGP_MIN}, {USD_EGP_MAX}]"
        )

    # التحقق من تاريخ البيانات
    date_str = data.get("date")
    if not date_str or not isinstance(date_str, str):
        raise ValueError("حقل التاريخ 'date' مفقود في استجابة Fawaz Currency API")

    try:
        data_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception as exc:
        raise ValueError(f"فشل تحليل صيغة تاريخ Fawaz '{date_str}': {exc}") from exc

    # حساب العمر بالأيام مقارنة بوقت الفحص
    current_date = now.date()
    age_days = (current_date - data_date).days

    if age_days > MAX_USD_AGE_DAYS:
        raise ValueError(
            f"بيانات سعر الدولار من Fawaz قديمة ({age_days} أيام مضت)، وتتجاوز الحد المسموح ({MAX_USD_AGE_DAYS} يوم)"
        )
    if age_days < 0:
        raise ValueError(f"تاريخ بيانات Fawaz يقع في المستقبل: {date_str}")

    return UsdRate(rate=rate, source_name="fawazahmed0", fetched_at=now)


def fetch_usd_fawaz() -> UsdRate:
    """جلب سعر صرف الدولار من المصدر الأساسي (Fawaz / jsDelivr)."""
    response = http_get(FAWAZ_USD_URL)
    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError(f"فشل فك تشفير JSON من Fawaz Currency API: {exc}") from exc

    return parse_usd_fawaz_response(data)
