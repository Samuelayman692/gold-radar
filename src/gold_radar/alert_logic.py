"""
منطق اتخاذ قرار إرسال التنبيهات (src/gold_radar/alert_logic.py).
لمشروع مرصاد الذهب (Gold Radar).

دوال نقية (pure functions) بالكامل وبدون أي اتصالات شبكية أو وصول لملفات،
تحدد ما إذا كان ينبغي إرسال تنبيه بناءً على حركة سعر الذهب لعيار 24 المعتمد،
مع كشف القفزات المشبوهة والتحقق من استقرارها قبل قبولها.
"""

from dataclasses import dataclass
from gold_radar.config import (
    ALERT_THRESHOLD_PCT,
    MAX_JUMP_PCT,
    SUSPICIOUS_CONFIRM_RUNS,
    SUSPICIOUS_CONFIRM_TOLERANCE_PCT,
)


@dataclass(frozen=True)
class AlertState:
    """حالة التنبيهات الحالية والمخزنة بين الدورات."""
    last_alert_price: float | None = None
    last_seen_price: float | None = None
    suspicious_count: int = 0
    last_suspicious_price: float | None = None


@dataclass(frozen=True)
class Decision:
    """قرار المنظومة بخصوص إرسال التنبيه والحالة الجديدة الواجب تخزينها."""
    action: str  # "first_alert" | "alert" | "none" | "suspicious"
    change_pct: float | None  # نسبة التغير المئوية بالنسبة لآخر سعر تنبيه (موقعة بإشارة + أو -)
    direction: str | None  # "up" | "down" | None
    new_state: AlertState


def _validate_price(price: float | int) -> float:
    """التحقق من أن السعر رقم موجب وصالح."""
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        raise ValueError(f"يجب أن يكون السعر رقماً صالحاً، القيمة المعطاة: {price!r}")
    num = float(price)
    if num <= 0.0:
        raise ValueError(f"يجب أن يكون السعر أكبر من الصفر، القيمة المعطاة: {price}")
    return num


def decide(current_price: float, state: AlertState | None = None) -> Decision:
    """
    تحديد قرار التنبيه بناءً على السعر الحالي والحالة السابقة:
    1. التحقق من صحة السعر (رقم موجب).
    2. في الدورة الأولى (last_alert_price فارغ): إرسال تنبيه البداية وتثبيت السعر.
    3. فحص القفزات المشبوهة (> MAX_JUMP_PCT): تصنيفها كمشبوهة وتجميد التنبيه إلا إذا استقرت وتأكدت.
    4. مقارنة السعر بآخر سعر تنبيه: إذا كانت النسبة >= ALERT_THRESHOLD_PCT يتم التنبيه وتحديث السعر.
    5. في الحالات العادية: تحديث last_seen_price وتصفير عداد الاشتباه.
    """
    c_price = _validate_price(current_price)

    if state is None:
        state = AlertState()

    # 1. الدورة الأولى (First Run)
    if state.last_alert_price is None:
        new_state = AlertState(
            last_alert_price=c_price,
            last_seen_price=c_price,
            suspicious_count=0,
            last_suspicious_price=None,
        )
        return Decision(
            action="first_alert",
            change_pct=None,
            direction=None,
            new_state=new_state,
        )

    # 2. فحص القفزات المشبوهة (Sanity Check vs last_seen_price or last_alert_price)
    base_price = state.last_seen_price if state.last_seen_price is not None else state.last_alert_price
    jump_pct = (abs(c_price - base_price) / base_price) * 100.0

    if jump_pct > MAX_JUMP_PCT:
        # فحص شرط الاستثناء: قفزة مستقرة تأكدت لعدد الدورات المطلوب
        is_confirmed = False
        if (
            state.suspicious_count + 1 >= SUSPICIOUS_CONFIRM_RUNS
            and state.last_suspicious_price is not None
        ):
            tolerance_diff = (
                abs(c_price - state.last_suspicious_price) / state.last_suspicious_price
            ) * 100.0
            if tolerance_diff <= SUSPICIOUS_CONFIRM_TOLERANCE_PCT:
                is_confirmed = True

        if not is_confirmed:
            # قفزة مشبوهة ولم تتأكد بعد: لا يتم التنبيه، ونزيد عداد الاشتباه
            new_state = AlertState(
                last_alert_price=state.last_alert_price,
                last_seen_price=state.last_seen_price,
                suspicious_count=state.suspicious_count + 1,
                last_suspicious_price=c_price,
            )
            return Decision(
                action="suspicious",
                change_pct=None,
                direction=None,
                new_state=new_state,
            )

    # 3. حساب نسبة التغير بالنسبة لآخر سعر تنبيه
    change_pct = ((c_price - state.last_alert_price) / state.last_alert_price) * 100.0

    if abs(change_pct) >= ALERT_THRESHOLD_PCT:
        action = "alert"
        direction = "up" if change_pct > 0.0 else "down"
        new_alert_price = c_price
    else:
        action = "none"
        direction = None
        new_alert_price = state.last_alert_price

    # 4. في كل الحالات غير المشبوهة (المؤكدة أو العادية)
    new_state = AlertState(
        last_alert_price=new_alert_price,
        last_seen_price=c_price,
        suspicious_count=0,
        last_suspicious_price=None,
    )

    return Decision(
        action=action,
        change_pct=change_pct,
        direction=direction,
        new_state=new_state,
    )
