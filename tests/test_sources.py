"""
اختبارات طبقة المصادر (tests/test_sources.py)
لمشروع مرصاد الذهب (Gold Radar).

تعتمد الاختبارات حصرياً على ملفات العينات المحفوظة (fixtures) دون أي اتصالات شبكية.
تختبر المحللات على البيانات السليمة وعلى البيانات المعطوبة (صفوف مفقودة، أسعار صفرية،
هيكل غير صالح، وتواريخ قديمة).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import pytest

# إضافة مجلد src إلى مسار استيراد الحزم
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gold_radar.sources.gold_api import parse_gold_api_response
from gold_radar.sources.isagha import parse_isagha_html
from gold_radar.sources.usd_er_api import parse_usd_er_api_response
from gold_radar.sources.usd_fawaz import parse_usd_fawaz_response

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# اختبارات Gold-API (سعر الأونصة العالمي)
# ---------------------------------------------------------------------------

def test_gold_api_good_data():
    """اختبار تحليل بيانات Gold-API السليمة من ملف العينة."""
    sample_path = FIXTURES_DIR / "gold_api_sample.json"
    with open(sample_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # محاكاة وقت فحص بعد دقيقتين من وقت التحديث (18:58:01 UTC)
    simulated_now = datetime(2026, 11, 18, 19, 0, 0, tzinfo=timezone.utc)
    res = parse_gold_api_response(data, now=simulated_now)

    assert res.usd == 3740.65
    assert res.fetched_at == simulated_now


def test_gold_api_old_data_raises_error():
    """البيانات التي يتجاوز عمرها 30 دقيقة يجب رفضها فوراً."""
    sample_path = FIXTURES_DIR / "gold_api_sample.json"
    with open(sample_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # محاكاة وقت بعد ساعتين (بيانات قديمة)
    future_now = datetime(2026, 11, 18, 21, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="قديمة جداً"):
        parse_gold_api_response(data, now=future_now)


def test_gold_api_missing_timestamp_or_only_relative():
    """إذا كان الطابع الزمني مفقوداً أو مجرد نص نسبي فقط، يجب رفضه."""
    data_no_ts = {"price": 3740.0}
    with pytest.raises(ValueError, match="لا تحتوي على طابع زمني"):
        parse_gold_api_response(data_no_ts)

    data_only_relative = {"price": 3740.0, "updatedAtReadable": "a few seconds ago"}
    with pytest.raises(ValueError, match="تحتوي فقط على نص وصفي نسبي"):
        parse_gold_api_response(data_only_relative)


@pytest.mark.parametrize("bad_price", [0, -100, 500.0, 50000.0, "3000", None, True])
def test_gold_api_invalid_price(bad_price):
    """الأسعار الصفرية أو السالبة أو الخارجة عن الحدود المنطقية يجب رفضها."""
    data = {
        "price": bad_price,
        "updatedAt": "2026-11-18T18:58:01Z",
    }
    simulated_now = datetime(2026, 11, 18, 19, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        parse_gold_api_response(data, now=simulated_now)


# ---------------------------------------------------------------------------
# اختبارات آي صاغة (iSagha - أسعار الذهب المحلية)
# ---------------------------------------------------------------------------

def test_isagha_good_data():
    """اختبار تحليل صفحة آي صاغة السليمة من ملف العينة."""
    sample_path = FIXTURES_DIR / "isagha_sample.html"
    with open(sample_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    simulated_now = datetime(2026, 11, 18, 19, 0, 0, tzinfo=timezone.utc)
    res = parse_isagha_html(html_content, now=simulated_now)

    assert res.buy_24k == 6554.25
    assert res.sell_24k == 6611.50
    assert res.buy_21k == 5735.00
    assert res.sell_21k == 5785.00
    assert res.buy_18k == 4915.75
    assert res.sell_18k == 4958.50
    assert res.buy_pound == 45880.00
    assert res.sell_pound == 46280.00
    assert res.fetched_at == simulated_now


def test_isagha_missing_row():
    """إذا نقص أي صف متوقع (مثل الجنيه الذهب أو عيار 24)، يجب رفع خطأ صريح."""
    # جدول ناقص صف الجنيه الذهب
    broken_html = """
    <table>
      <tr><td>عيار 24</td><td>6550</td><td>6610</td></tr>
      <tr><td>عيار 21</td><td>5730</td><td>5780</td></tr>
      <tr><td>عيار 18</td><td>4910</td><td>4950</td></tr>
    </table>
    """
    with pytest.raises(ValueError, match="مفقودة"):
        parse_isagha_html(broken_html)


def test_isagha_sell_lower_than_buy():
    """سعر البيع أقل من سعر الشراء يعتبر خللاً جسيماً ويجب رفضه."""
    inverted_prices_html = """
    <table>
      <tr><td>عيار 24</td><td>6650</td><td>6600</td></tr>
      <tr><td>عيار 21</td><td>5730</td><td>5780</td></tr>
      <tr><td>عيار 18</td><td>4910</td><td>4950</td></tr>
      <tr><td>جنيه ذهب</td><td>45800</td><td>46200</td></tr>
    </table>
    """
    with pytest.raises(ValueError, match="أقل من سعر الشراء"):
        parse_isagha_html(inverted_prices_html)


@pytest.mark.parametrize("zero_val", ["0", "-10"])
def test_isagha_zero_or_negative_price(zero_val):
    """الأسعار الصفرية أو السالبة يجب رفضها."""
    bad_html = f"""
    <table>
      <tr><td>عيار 24</td><td>{zero_val}</td><td>6600</td></tr>
      <tr><td>عيار 21</td><td>5730</td><td>5780</td></tr>
      <tr><td>عيار 18</td><td>4910</td><td>4950</td></tr>
      <tr><td>جنيه ذهب</td><td>45800</td><td>46200</td></tr>
    </table>
    """
    with pytest.raises(ValueError, match="يجب أن يكون أكبر من الصفر"):
        parse_isagha_html(bad_html)


def test_isagha_empty_or_broken_html():
    """المدخلات الفارغة لآي صاغة يجب أن ترفع خطأ."""
    with pytest.raises(ValueError):
        parse_isagha_html("")
    with pytest.raises(ValueError):
        parse_isagha_html("<html><body><p>لا توجد جداول هنا</p></body></html>")


# ---------------------------------------------------------------------------
# اختبارات مصدر Fawaz للدولار (USD Primary)
# ---------------------------------------------------------------------------

def test_usd_fawaz_good_data():
    """اختبار تحليل بيانات Fawaz السليمة من ملف العينة."""
    sample_path = FIXTURES_DIR / "usd_fawaz_sample.json"
    with open(sample_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    simulated_now = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
    res = parse_usd_fawaz_response(data, now=simulated_now)

    assert abs(res.rate - 53.7393) < 0.001
    assert res.source_name == "fawazahmed0"
    assert res.fetched_at == simulated_now


def test_usd_fawaz_old_date():
    """إذا كان تاريخ بيانات Fawaz أقدم من يومين، يجب رفضها."""
    sample_path = FIXTURES_DIR / "usd_fawaz_sample.json"
    with open(sample_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # تاريخ العينة هو 2026-11-18، نختبر وقت بعد 4 أيام (2026-11-22)
    late_now = datetime(2026, 11, 22, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="قديمة"):
        parse_usd_fawaz_response(data, now=late_now)


@pytest.mark.parametrize("bad_rate", [0, -50, 10.0, 200.0, None, True])
def test_usd_fawaz_invalid_rate(bad_rate):
    """أسعار الدولار غير الرقمية أو الخارجة عن الحدود المنطقية يجب رفضها."""
    data = {"date": "2026-11-18", "usd": {"egp": bad_rate}}
    simulated_now = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        parse_usd_fawaz_response(data, now=simulated_now)


# ---------------------------------------------------------------------------
# اختبارات مصدر open.er-api للدولار (USD Fallback)
# ---------------------------------------------------------------------------

def test_usd_er_api_good_data():
    """اختبار تحليل بيانات open.er-api السليمة من ملف العينة."""
    sample_path = FIXTURES_DIR / "usd_er_api_sample.json"
    with open(sample_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    simulated_now = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
    res = parse_usd_er_api_response(data, now=simulated_now)

    assert abs(res.rate - 53.7177) < 0.001
    assert res.source_name == "open.er-api.com"
    assert res.fetched_at == simulated_now


def test_usd_er_api_failure_result():
    """إذا كان حقل result لا يساوي success، يجب رفع خطأ."""
    data = {"result": "error", "error-type": "invalid-key"}
    with pytest.raises(ValueError, match="تفيد بعدم النجاح"):
        parse_usd_er_api_response(data)


def test_usd_er_api_old_date():
    """إذا كان تاريخ open.er-api أقدم من يومين، يجب رفضه."""
    sample_path = FIXTURES_DIR / "usd_er_api_sample.json"
    with open(sample_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # بعد 5 أيام
    late_now = datetime(2026, 11, 23, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="قديمة"):
        parse_usd_er_api_response(data, now=late_now)


@pytest.mark.parametrize("bad_rate", [0, -50, 10.0, 200.0, None, True])
def test_usd_er_api_invalid_rate(bad_rate):
    """أسعار الدولار غير الرقمية أو الشاذة في open.er-api يجب رفضها."""
    data = {
        "result": "success",
        "time_last_update_utc": "Wed, 18 Nov 2026 00:02:31 +0000",
        "rates": {"EGP": bad_rate},
    }
    simulated_now = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        parse_usd_er_api_response(data, now=simulated_now)
