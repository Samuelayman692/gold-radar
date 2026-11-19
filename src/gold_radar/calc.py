"""
دوال الحسابات الرياضية النقية (src/gold_radar/calc.py)
لمشروع مرصاد الذهب (Gold Radar).

جميع الدوال هنا نقية (pure functions) تماماً وبدون أي اتصالات شبكية،
مع التحقق الصارم من صحة المدخلات ورفع ValueError عند وجود أخطاء.
"""

from gold_radar.config import BALANCED_GAP_PCT, GOLD_POUND_GRAMS_21K, GRAMS_PER_TROY_OUNCE


def _validate_number(name: str, value: float | int) -> float:
    """التحقق من أن القيمة رقمية وليست قيمة منطقية (bool)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"يجب أن تكون قيمة '{name}' رقماً صالحاً، القيمة المعطاة: {value!r}")
    return float(value)


def _validate_positive(name: str, value: float | int) -> float:
    """التحقق من أن القيمة رقمية وموجبة تماماً (أكبر من الصفر)."""
    num = _validate_number(name, value)
    if num <= 0.0:
        raise ValueError(f"يجب أن تكون قيمة '{name}' أكبر من الصفر، القيمة المعطاة: {value}")
    return num


def fair_price_24k(ounce_usd: float, usd_egp: float) -> float:
    """
    حساب السعر العادل لجرام الذهب عيار 24 بالجنيه المصري:
    fair_price_24k = ounce_usd * usd_egp / GRAMS_PER_TROY_OUNCE
    """
    o_usd = _validate_positive("ounce_usd", ounce_usd)
    u_egp = _validate_positive("usd_egp", usd_egp)
    return (o_usd * u_egp) / GRAMS_PER_TROY_OUNCE


def gap(local_price: float, fair_price: float) -> tuple[float, float]:
    """
    حساب الفجوة السعرية بين السعر المحلي والسعر العادل:
    - gap_egp: الفارق بالجنيه المصري (السعر المحلي - السعر العادل)
    - gap_pct: النسبة المئوية للفجوة بالنسبة للسعر العادل
    """
    l_price = _validate_positive("local_price", local_price)
    f_price = _validate_positive("fair_price", fair_price)

    gap_egp = l_price - f_price
    gap_pct = (gap_egp / f_price) * 100.0
    return gap_egp, gap_pct


def market_status(gap_pct: float, balanced_pct: float = BALANCED_GAP_PCT) -> str:
    """
    تحديد حالة السوق مقارنة بالسعر العالمي:
    - 'balanced' إذا كانت الفجوة ضمن النطاق المقبول (abs(gap_pct) < balanced_pct)
    - 'higher' إذا كان السعر المحلي أعلى (gap_pct >= balanced_pct)
    - 'lower' إذا كان السعر المحلي أقل (gap_pct <= -balanced_pct)
    """
    g_pct = _validate_number("gap_pct", gap_pct)
    b_pct = _validate_positive("balanced_pct", balanced_pct)

    if g_pct >= b_pct:
        return "higher"
    elif g_pct <= -b_pct:
        return "lower"
    else:
        return "balanced"


def derived_karat_price(price_24k: float, karat: int | float) -> float:
    """
    حساب سعر أي عيار مشتقاً من سعر عيار 24:
    derived_karat_price = price_24k * karat / 24
    """
    p24 = _validate_positive("price_24k", price_24k)
    k = _validate_positive("karat", karat)
    return (p24 * k) / 24.0


def gold_pound_price(price_21k: float) -> float:
    """
    حساب سعر الجنيه الذهب الرسمي (8 جرامات عيار 21):
    gold_pound_price = price_21k * 8
    """
    p21 = _validate_positive("price_21k", price_21k)
    return p21 * GOLD_POUND_GRAMS_21K
