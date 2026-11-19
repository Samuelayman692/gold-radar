"""
مصدر أسعار الذهب المحلية من منصة آي صاغة (src/gold_radar/sources/isagha.py).
يجلب الصفحة الثابتة من https://market.isagha.com/ ويحللها بصرامة.
يستخرج أسعار البيع والشراء لعيارات 24 و 21 و 18 والجنيه الذهب فقط،
ويرفع خطأ صريحاً إذا حدث أي تغيير في بنية الصفحة أو نَقَصَ أي صف متوقع.
"""

from datetime import datetime, timezone
from bs4 import BeautifulSoup

from gold_radar.config import PRICE_24K_MAX, PRICE_24K_MIN
from gold_radar.sources.http import http_get
from gold_radar.sources.models import LocalPrices

ISAGHA_URL = "https://market.isagha.com/"


def parse_isagha_html(html_text: str, now: datetime | None = None) -> LocalPrices:
    """
    تحليل كود HTML لصفحة آي صاغة والتحقق الصارم من توفر كافة العيارات المطلوبة وسلامة الأسعار.
    دالة نقية تقبل وقت 'now' لتسهيل اختبارات الوحدة المعزولة.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if not html_text or not isinstance(html_text, str):
        raise ValueError("محتوى HTML الخاص بآي صاغة فارغ أو غير صالح")

    soup = BeautifulSoup(html_text, "html.parser")

    # قواميس لتخزين القيم المستخرجة
    extracted = {}

    for tr in soup.find_all("tr"):
        cols = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if len(cols) < 3:
            continue

        item_name = cols[0]
        try:
            buy_val = float(cols[1].replace(",", ""))
            sell_val = float(cols[2].replace(",", ""))
        except (ValueError, TypeError):
            continue

        if "24" in item_name and "عيار" in item_name:
            extracted["24k"] = (buy_val, sell_val)
        elif "21" in item_name and "عيار" in item_name:
            extracted["21k"] = (buy_val, sell_val)
        elif "18" in item_name and "عيار" in item_name:
            extracted["18k"] = (buy_val, sell_val)
        elif "جنيه" in item_name:
            extracted["pound"] = (buy_val, sell_val)

    # التحقق الصارم من وجود جميع الصفوف الأربعة المطلوبة
    required_keys = ["24k", "21k", "18k", "pound"]
    missing = [k for k in required_keys if k not in extracted]
    if missing:
        raise ValueError(
            f"فشل استخراج أسعار الذهب من آي صاغة: الصفوف التالية مفقودة أو تغيرت بنيتها: {missing}"
        )

    b24, s24 = extracted["24k"]
    b21, s21 = extracted["21k"]
    b18, s18 = extracted["18k"]
    bpound, spound = extracted["pound"]

    # التحقق من أن جميع الأسعار موجبة ومنطقية
    for name, buy, sell in [
        ("عيار 24", b24, s24),
        ("عيار 21", b21, s21),
        ("عيار 18", b18, s18),
        ("الجنيه الذهب", bpound, spound),
    ]:
        if buy <= 0 or sell <= 0:
            raise ValueError(f"سعر {name} غير صالح (يجب أن يكون أكبر من الصفر): شراء={buy}, بيع={sell}")
        if sell < buy:
            raise ValueError(f"سعر بيع {name} ({sell}) أقل من سعر الشراء ({buy}) وهذا غير منطقي")

    # فحص النطاق المنطقي لسعر عيار 24
    if not (PRICE_24K_MIN <= s24 <= PRICE_24K_MAX):
        raise ValueError(
            f"سعر بيع عيار 24 ({s24} ج.م) خارج النطاق المنطقي المسموح [{PRICE_24K_MIN}, {PRICE_24K_MAX}]"
        )

    return LocalPrices(
        buy_24k=b24,
        sell_24k=s24,
        buy_21k=b21,
        sell_21k=s21,
        buy_18k=b18,
        sell_18k=s18,
        buy_pound=bpound,
        sell_pound=spound,
        fetched_at=now,
    )


def fetch_local_prices() -> LocalPrices:
    """جلب وتحليل أسعار الذهب لحظياً من منصة آي صاغة."""
    response = http_get(ISAGHA_URL)
    return parse_isagha_html(response.text)
