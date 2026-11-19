"""
اختبارات وحدة منطق التنبيهات (tests/test_alert_logic.py)
لمشروع مرصاد الذهب (Gold Radar).

اختبارات نقية بدون أي اتصالات شبكية، تغطي كافة سيناريوهات اتخاذ القرار:
الدورة الأولى، ثبات الأسعار، تغيرات طفيفة، الحدود الدقيقة للتنبيه (0.25%)،
تحديث سعر التنبيه، كشف القفزات المشبوهة، رفضها، أو قبولها عند استقرارها.
"""

import sys
from pathlib import Path
import pytest

# إضافة مجلد src لمسار الحزم
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gold_radar.alert_logic import AlertState, decide


def test_first_run():
    """الدورة الأولى: يجب أن تعطي action='first_alert' وتثبت السعر."""
    state = AlertState()
    decision = decide(6000.0, state)

    assert decision.action == "first_alert"
    assert decision.change_pct is None
    assert decision.direction is None
    assert decision.new_state.last_alert_price == 6000.0
    assert decision.new_state.last_seen_price == 6000.0
    assert decision.new_state.suspicious_count == 0
    assert decision.new_state.last_suspicious_price is None


def test_no_change():
    """ثبات السعر تماماً: action='none' وبدون أي تغيير في الحالة."""
    state = AlertState(last_alert_price=6000.0, last_seen_price=6000.0)
    decision = decide(6000.0, state)

    assert decision.action == "none"
    assert decision.change_pct == 0.0
    assert decision.direction is None
    assert decision.new_state.last_alert_price == 6000.0
    assert decision.new_state.last_seen_price == 6000.0


def test_tiny_change_below_threshold():
    """تغير طفيف أقل من 0.25%: action='none' وسعر التنبيه يبقى كما هو."""
    # ارتفاع بمقدار 10 جنيهات (0.167%)
    state = AlertState(last_alert_price=6000.0, last_seen_price=6000.0)
    decision = decide(6010.0, state)

    assert decision.action == "none"
    assert decision.direction is None
    assert 0.0 < decision.change_pct < 0.25
    assert decision.new_state.last_alert_price == 6000.0
    assert decision.new_state.last_seen_price == 6010.0


def test_exact_boundary_triggers():
    """الحد الفاصل بالضبط (±0.25%) يجب أن يطلق التنبيه."""
    base_state = AlertState(last_alert_price=6000.0, last_seen_price=6000.0)

    # 1. صعود بنسبة 0.25% بالضبط: 6000 * 1.0025 = 6015.0
    dec_up = decide(6015.0, base_state)
    assert dec_up.action == "alert"
    assert dec_up.direction == "up"
    assert dec_up.change_pct == 0.25
    assert dec_up.new_state.last_alert_price == 6015.0

    # 2. هبوط بنسبة 0.25% بالضبط: 6000 * 0.9975 = 5985.0
    dec_down = decide(5985.0, base_state)
    assert dec_down.action == "alert"
    assert dec_down.direction == "down"
    assert dec_down.change_pct == -0.25
    assert dec_down.new_state.last_alert_price == 5985.0

    # 3. قبل الحد بشعرة: 6014.94 (0.249%) لا يجب أن ينبه
    dec_sub = decide(6014.94, base_state)
    assert dec_sub.action == "none"
    assert dec_sub.direction is None


def test_clear_change_up_and_down():
    """تغير واضح صعوداً وهبوطاً: يطلق تنبيه بالاتجاه الصحيح."""
    base_state = AlertState(last_alert_price=6000.0, last_seen_price=6000.0)

    # صعود واضح (+1.0%)
    dec_up = decide(6060.0, base_state)
    assert dec_up.action == "alert"
    assert dec_up.direction == "up"
    assert dec_up.change_pct == 1.0
    assert dec_up.new_state.last_alert_price == 6060.0

    # هبوط واضح (-1.0%)
    dec_down = decide(5940.0, base_state)
    assert dec_down.action == "alert"
    assert dec_down.direction == "down"
    assert dec_down.change_pct == -1.0
    assert dec_down.new_state.last_alert_price == 5940.0


def test_subsequent_comparison_uses_new_alert_price():
    """بعد التنبيه، المقارنة اللاحقة تعتمد على السعر الجديد للتنبيه."""
    # التنبيه الأول عند 6015.0
    state1 = AlertState(last_alert_price=6000.0, last_seen_price=6000.0)
    dec1 = decide(6015.0, state1)
    assert dec1.action == "alert"
    state2 = dec1.new_state
    assert state2.last_alert_price == 6015.0

    # فحص سعر 6020.0: التغير بالنسبة لـ 6015 هو +0.083% (أقل من 0.25% فلا ينبه)
    dec2 = decide(6020.0, state2)
    assert dec2.action == "none"
    assert dec2.new_state.last_alert_price == 6015.0
    state3 = dec2.new_state

    # فحص سعر 6035.0: التغير بالنسبة لـ 6015 هو +0.33% (أكبر من 0.25% فينبه)
    dec3 = decide(6035.0, state3)
    assert dec3.action == "alert"
    assert dec3.direction == "up"
    assert dec3.new_state.last_alert_price == 6035.0


def test_suspicious_jump_triggers_suspicious_action():
    """قفزة 6% تعتبر مشبوهة (> 5%) ولا تغير last_alert_price."""
    state = AlertState(last_alert_price=6000.0, last_seen_price=6000.0)
    # 6000 -> 6360 هي قفزة 6.0%
    decision = decide(6360.0, state)

    assert decision.action == "suspicious"
    assert decision.direction is None
    assert decision.new_state.last_alert_price == 6000.0  # لم يتغير
    assert decision.new_state.last_seen_price == 6000.0   # لم يتغير
    assert decision.new_state.suspicious_count == 1
    assert decision.new_state.last_suspicious_price == 6360.0


def test_suspicious_blip_then_normal_resets_counters():
    """قفزة مشبوهة تلاها سعر طبيعي تعود الحالة طبيعية ويصفر العداد."""
    # الحالة الحالية بعد قفزة مشبوهة
    suspicious_state = AlertState(
        last_alert_price=6000.0,
        last_seen_price=6000.0,
        suspicious_count=1,
        last_suspicious_price=6360.0,
    )

    # السعر عاد طبيعياً إلى 6005.0
    decision = decide(6005.0, suspicious_state)

    assert decision.action == "none"
    assert decision.direction is None
    assert decision.new_state.last_alert_price == 6000.0
    assert decision.new_state.last_seen_price == 6005.0
    assert decision.new_state.suspicious_count == 0
    assert decision.new_state.last_suspicious_price is None


def test_stable_suspicious_jump_is_confirmed_and_alerts():
    """قفزة 6% استقرت في الدورة الثانية (ضمن 1%) يتم تأكيدها وإرسال التنبيه."""
    # الدورة 1: قفزة مشبوهة أولى إلى 6360.0
    state1 = AlertState(last_alert_price=6000.0, last_seen_price=6000.0)
    dec1 = decide(6360.0, state1)
    assert dec1.action == "suspicious"

    # الدورة 2: السعر استقر عند 6365.0 (فارق 5 جنيهات عن 6360 أي 0.08% <= 1%)
    dec2 = decide(6365.0, dec1.new_state)

    assert dec2.action == "alert"
    assert dec2.direction == "up"
    assert dec2.change_pct > 5.0
    assert dec2.new_state.last_alert_price == 6365.0
    assert dec2.new_state.last_seen_price == 6365.0
    assert dec2.new_state.suspicious_count == 0
    assert dec2.new_state.last_suspicious_price is None


def test_unstable_second_suspicious_value_not_accepted():
    """قيمة مشبوهة ثانية تختلف بأكثر من 1% عن الأولى لا يتم تأكيدها وتبقى مشبوهة."""
    # بعد قفزة أولى إلى 6360.0
    state_after_run1 = AlertState(
        last_alert_price=6000.0,
        last_seen_price=6000.0,
        suspicious_count=1,
        last_suspicious_price=6360.0,
    )

    # الدورة 2: قفز السعر إلى 6500.0 (فارق 2.2% عن 6360 أي > 1%)
    dec2 = decide(6500.0, state_after_run1)

    assert dec2.action == "suspicious"
    assert dec2.direction is None
    assert dec2.new_state.last_alert_price == 6000.0  # ما زال غير مثبت
    assert dec2.new_state.suspicious_count == 2
    assert dec2.new_state.last_suspicious_price == 6500.0


@pytest.mark.parametrize("invalid_val", [0, -10, -0.01, "6000", None, True, False])
def test_invalid_price_raises_value_error(invalid_val):
    """الأسعار الصفرية، السالبة، أو غير الرقمية يجب أن ترفع ValueError."""
    state = AlertState(last_alert_price=6000.0, last_seen_price=6000.0)
    with pytest.raises(ValueError):
        decide(invalid_val, state)
