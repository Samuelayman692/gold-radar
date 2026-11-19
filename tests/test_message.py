"""
اختبارات وحدة بناء وتنسيق الرسائل (tests/test_message.py)
لمشروع مرصاد الذهب (Gold Radar).

اختبارات نقية بدون أي اتصالات شبكية، تتحقق من التطابق التام لنص الرسالة،
إشارات الفجوة (+ و -)، حالات السوق الثلاث، دقة التحويل الزمني للقاهرة (صيفاً وشتاءً)،
وجود وسم 'محسوب' لعيار 14 فقط، ورفض المدخلات الخاطئة.
"""

from datetime import datetime, timezone
import sys
from pathlib import Path
import pytest

# إضافة مجلد src لمسار الحزم
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gold_radar.message import MessageData, build_message


def _create_sample_data(**kwargs) -> MessageData:
    """مساعد لإنشاء كائن MessageData مع قيم افتراضية سليمة."""
    defaults = {
        "price_24k": 6611.50,
        "price_21k": 5785.00,
        "price_18k": 4958.50,
        "price_14k": 3856.71,
        "gold_pound": 46280.00,
        "ounce_usd": 3740.65,
        "usd_egp": 53.72,
        "fair_24k": 6459.73,
        "gap_egp": 151.77,
        "gap_pct": 2.35,
        "status": "higher",
        "updated_at_utc": datetime(2026, 11, 18, 19, 30, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return MessageData(**defaults)


def test_full_message_exact_layout():
    """التحقق من التطابق التام والسطري لنص الرسالة مع التنسيق المطلوب."""
    data = _create_sample_data()
    msg = build_message(data)

    expected = (
        "🟡 مرصاد الذهب\n"
        "💰 السعر المحلي ع24 : 6,611.50 ج.م\n"
        "💰 السعر المحلي ع21 : 5,785.00 ج.م\n"
        "💰 السعر المحلي ع18 : 4,958.50 ج.م\n"
        "💰 السعر المحلي ع14 : 3,856.71 ج.م (محسوب)\n"
        "🪙 الجنيه الذهب : 46,280.00 ج.م\n"
        "🌍 الأونصة عالمياً : $3,740.65\n"
        "💵 سعر الدولار (المركزي) : 53.72 ج.م\n"
        "⚖️ السعر العادل ع24 : 6,459.73 ج.م\n"
        "📈 الفجوة السعرية : +151.77 ج.م (+2.35%)\n"
        "📊 حالة السوق : أعلى\n"
        "🕐 آخر تحديث : 2026-11-18 21:30\n"
        "مؤشر للمتابعة وليس نصيحة استثمارية."
    )

    assert msg == expected


def test_gap_sign_display():
    """التحقق من إظهار إشارة الموجب (+) والسالب (-) الصريحة للفجوة ونسبتها."""
    # فجوة موجبة
    pos_data = _create_sample_data(gap_egp=50.25, gap_pct=0.78)
    pos_msg = build_message(pos_data)
    assert "📈 الفجوة السعرية : +50.25 ج.م (+0.78%)" in pos_msg

    # فجوة سالبة
    neg_data = _create_sample_data(gap_egp=-50.25, gap_pct=-0.78)
    neg_msg = build_message(neg_data)
    assert "📈 الفجوة السعرية : -50.25 ج.م (-0.78%)" in neg_msg


@pytest.mark.parametrize(
    "status_en, status_ar",
    [
        ("higher", "أعلى"),
        ("lower", "أقل"),
        ("balanced", "متوازن"),
    ],
)
def test_all_market_statuses(status_en, status_ar):
    """التحقق من صحة تعريب حالات السوق الثلاث."""
    data = _create_sample_data(status=status_en)
    msg = build_message(data)
    assert f"📊 حالة السوق : {status_ar}" in msg


def test_cairo_timezone_conversion_winter_and_summer():
    """التحقق من التحويل الزمني لتوقيت القاهرة شتاءً (UTC+2) وصيفاً مع التوقيت الصيفي (UTC+3)."""
    # شتاءً: يناير (UTC+2) -> 10:30 UTC تصبح 12:30
    winter_utc = datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc)
    winter_msg = build_message(_create_sample_data(updated_at_utc=winter_utc))
    assert "🕐 آخر تحديث : 2026-01-15 12:30" in winter_msg

    # صيفاً: يوليو (UTC+3 بموجب التوقيت الصيفي) -> 10:30 UTC تصبح 13:30
    summer_utc = datetime(2026, 7, 15, 10, 30, tzinfo=timezone.utc)
    summer_msg = build_message(_create_sample_data(updated_at_utc=summer_utc))
    assert "🕐 آخر تحديث : 2026-07-15 13:30" in summer_msg


def test_only_14k_has_calculated_tag():
    """التحقق من أن كلمة 'محسوب' تظهر فقط في سطر عيار 14 ولا تتكرر في أي سطر آخر."""
    msg = build_message(_create_sample_data())
    lines = msg.splitlines()

    # السطر الذي يحتوي على 'محسوب' يجب أن يكون حصرياً سطر عيار 14
    for line in lines:
        if "محسوب" in line:
            assert "ع14" in line

    assert msg.count("محسوب") == 1


@pytest.mark.parametrize("invalid_price", [0, -100, float("nan"), float("inf"), None, True, "5000"])
def test_invalid_prices_raise_value_error(invalid_price):
    """الأسعار الصفرية أو السالبة أو غير الصالحة أو NaN ترفع خطأ ValueError."""
    with pytest.raises(ValueError):
        _create_sample_data(price_24k=invalid_price)
        build_message(_create_sample_data(price_24k=invalid_price))

    with pytest.raises(ValueError):
        build_message(_create_sample_data(price_14k=invalid_price))

    with pytest.raises(ValueError):
        build_message(_create_sample_data(ounce_usd=invalid_price))


def test_unknown_status_raises_value_error():
    """حالة سوق غير معروفة ترفع ValueError."""
    with pytest.raises(ValueError, match="حالة السوق غير معروفة"):
        build_message(_create_sample_data(status="neutral"))


def test_naive_datetime_raises_value_error():
    """التاريخ غير الواعي (بدون timezone) يرفع ValueError."""
    naive_dt = datetime(2026, 11, 18, 12, 0)  # no tzinfo
    with pytest.raises(ValueError, match="منطقة زمنية واعية"):
        build_message(_create_sample_data(updated_at_utc=naive_dt))
