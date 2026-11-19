"""
المجمع الموحد لسعر صرف الدولار (src/gold_radar/sources/usd.py).
يحاول أولاً الجلب من المصدر الأساسي (Fawaz Currency API)،
وفي حال فشله ينتقل بسلاسة للمصدر الاحتياطي (open.er-api.com).
وفقاً للقاعدة 6 لا يتم استدعاء المصدر الاحتياطي طالما نجح الأساسي تجنباً لأي طلبات شبكية إضافية.
"""

from gold_radar.sources.models import UsdRate
from gold_radar.sources.usd_er_api import fetch_usd_er_api
from gold_radar.sources.usd_fawaz import fetch_usd_fawaz


def get_usd_rate() -> UsdRate:
    """
    الحصول على سعر صرف الدولار مقابل الجنيه المصري:
    1. محاولة الجلب من المصدر الأساسي (Fawaz Ahmed API عبر CDN).
    2. في حال الفشل أو عدم صحة البيانات، التحول للمصدر الاحتياطي (open.er-api.com).
    """
    primary_error: Exception | None = None

    # محاولة المصدر الأساسي
    try:
        return fetch_usd_fawaz()
    except Exception as exc:
        primary_error = exc

    # التحول للمصدر الاحتياطي عند فشل الأساسي
    try:
        return fetch_usd_er_api()
    except Exception as fallback_exc:
        raise RuntimeError(
            f"فشل جلب سعر الدولار من كلا المصدرين:\n"
            f"- الأساسي (Fawaz): {primary_error}\n"
            f"- الاحتياطي (open.er-api): {fallback_exc}"
        ) from fallback_exc
