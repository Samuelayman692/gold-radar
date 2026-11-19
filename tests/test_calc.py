"""
اختبارات وحدة الحسابات (tests/test_calc.py)
لمشروع مرصاد الذهب (Gold Radar).

اختبارات نقية بدون أي اتصالات شبكية وتستخدم أرقاماً معروفة وبسيطة.
"""

import sys
from pathlib import Path
import pytest

# إضافة مجلد src إلى مسار استيراد الحزم
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gold_radar.calc import (
    derived_karat_price,
    fair_price_24k,
    gap,
    gold_pound_price,
    market_status,
)


def test_fair_price_24k():
    """أونصة 3110.35 ودولار 50 يعطي سعراً عادلاً 5000 ج.م تماماً."""
    ounce_usd = 3110.35
    usd_egp = 50.0
    price = fair_price_24k(ounce_usd, usd_egp)
    assert price == 5000.0


def test_gap():
    """سعر محلي 5050 وسعر عادل 5000 يعطي فجوة 50 ج.م ونسبة 1.0% تماماً."""
    local_price = 5050.0
    fair_price = 5000.0
    gap_egp, gap_pct = gap(local_price, fair_price)
    assert gap_egp == 50.0
    assert gap_pct == 1.0


def test_market_status_boundaries():
    """
    اختبار حالات السوق (higher / lower / balanced) بما في ذلك الحدود الفاصلة:
    - balanced_pct = 1.0
    - عند الحد بالضبط 1.0% -> higher
    - عند الحد بالضبط -1.0% -> lower
    - داخل النطاق (-1.0%, 1.0%) -> balanced
    """
    balanced_limit = 1.0

    # الحدود الفاصلة بالضبط
    assert market_status(1.0, balanced_limit) == "higher"
    assert market_status(-1.0, balanced_limit) == "lower"

    # أعلى من النطاق
    assert market_status(1.5, balanced_limit) == "higher"
    assert market_status(2.0, balanced_limit) == "higher"

    # أقل من النطاق
    assert market_status(-1.5, balanced_limit) == "lower"
    assert market_status(-2.5, balanced_limit) == "lower"

    # داخل النطاق المتوازن (abs(gap_pct) < 1.0)
    assert market_status(0.99, balanced_limit) == "balanced"
    assert market_status(0.0, balanced_limit) == "balanced"
    assert market_status(-0.99, balanced_limit) == "balanced"


def test_derived_karat_prices():
    """عيار 24 بسعر 6000 يعطي: 21k=5250 و 18k=4500 و 14k=3500."""
    price_24k = 6000.0
    assert derived_karat_price(price_24k, 21) == 5250.0
    assert derived_karat_price(price_24k, 18) == 4500.0
    assert derived_karat_price(price_24k, 14) == 3500.0


def test_gold_pound_price():
    """الجنيه الذهب (8 جرامات عيار 21) عند سعر 21k = 5250 يعطي 42000 ج.م تماماً."""
    price_21k = 5250.0
    assert gold_pound_price(price_21k) == 42000.0


@pytest.mark.parametrize(
    "invalid_val",
    [0, -1, -50.5, "5000", None, True, False],
)
def test_invalid_inputs_raise_value_error(invalid_val):
    """القيم الصفرية، السالبة، أو غير الرقمية يجب أن ترفع ValueError."""
    # fair_price_24k
    with pytest.raises(ValueError):
        fair_price_24k(invalid_val, 50.0)
    with pytest.raises(ValueError):
        fair_price_24k(3110.35, invalid_val)

    # gap
    with pytest.raises(ValueError):
        gap(invalid_val, 5000.0)
    with pytest.raises(ValueError):
        gap(5050.0, invalid_val)

    # derived_karat_price
    with pytest.raises(ValueError):
        derived_karat_price(invalid_val, 21)
    with pytest.raises(ValueError):
        derived_karat_price(6000.0, invalid_val)

    # gold_pound_price
    with pytest.raises(ValueError):
        gold_pound_price(invalid_val)


def test_market_status_invalid_inputs():
    """التحقق من صحة مدخلات market_status."""
    # balanced_pct لا يمكن أن يكون سالباً أو صفراً أو غير رقمي
    with pytest.raises(ValueError):
        market_status(0.5, 0.0)
    with pytest.raises(ValueError):
        market_status(0.5, -1.0)
    with pytest.raises(ValueError):
        market_status(0.5, "1.0")
    with pytest.raises(ValueError):
        market_status(0.5, True)

    # gap_pct لا يمكن أن يكون غير رقمي
    with pytest.raises(ValueError):
        market_status("0.5", 1.0)
    with pytest.raises(ValueError):
        market_status(None, 1.0)
    with pytest.raises(ValueError):
        market_status(False, 1.0)
