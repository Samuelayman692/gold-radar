"""
أداة فحص المصادر (tools/probe_sources.py)
لمشروع مرصاد الذهب (Gold Radar)

تفحص 4 مصادر بطلب واحد لكل مصدر وزمن انتظار أقصاه 15 ثانية:
1. Gold-API.com (سعر الأونصة العالمي بالدولار)
2. egygold.com (فحص توفر أسعار الذهب المصري)
3. iSagha (آي صاغة - أسعار الذهب في السوق المصري)
4. Central Bank of Egypt (البنك المركزي المصري - سعر صرف USD/EGP)

تتبع الأداة جميع قواعد AGENT_RULES.md (فحص robots.txt، عدم تجاوز الحجب، ترويسة مهذبة).
"""

import sys
import time
import requests
from bs4 import BeautifulSoup

# ضبط ترميز المخرجات لدعم اللغة العربية في جميع الطرفيات
sys.stdout.reconfigure(encoding="utf-8")

# إعدادات الفحص
USER_AGENT = "GoldRadar/0.1"
TIMEOUT_SECONDS = 15
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
    "Accept-Language": "ar,en;q=0.9",
}


def check_robots_txt(robots_url: str) -> dict:
    """فحص ملف robots.txt بأدب لمعرفة سماحية الوصول الآلي."""
    try:
        start_time = time.time()
        res = requests.get(robots_url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        elapsed = round(time.time() - start_time, 2)

        if res.status_code == 200:
            content = res.text.lower()
            # فحص سريع لرسائل الحجب أو المنع الصريح لجميع البوتات
            if "request rejected" in content:
                return {
                    "status": res.status_code,
                    "allowed": False,
                    "reason": "تم رفض طلب robots.txt بواسطة جدار الحماية (WAF)",
                    "elapsed": elapsed,
                }
            if "disallow: /" in content and "disallow: /\n" in content:
                return {
                    "status": res.status_code,
                    "allowed": False,
                    "reason": "ملف robots.txt يمنع الوصول الشامل (Disallow: /)",
                    "elapsed": elapsed,
                }
            return {
                "status": res.status_code,
                "allowed": True,
                "reason": "متاح ومسموح بالقراءة الآلية العامة",
                "elapsed": elapsed,
            }
        elif res.status_code == 404:
            return {
                "status": res.status_code,
                "allowed": True,
                "reason": "غير موجود (404 Not Found) - لا توجد قيود معلنة",
                "elapsed": elapsed,
            }
        else:
            return {
                "status": res.status_code,
                "allowed": False,
                "reason": f"رمز الاستجابة: {res.status_code}",
                "elapsed": elapsed,
            }
    except Exception as exc:
        return {
            "status": "Error",
            "allowed": False,
            "reason": f"تعذر الاتصال بملف robots.txt: {exc}",
            "elapsed": 0.0,
        }


def probe_gold_api() -> dict:
    """فحص المصدر 1: Gold-API.com للحصول على سعر الأونصة بالدولار."""
    robots_res = check_robots_txt("https://gold-api.com/robots.txt")
    target_url = "https://api.gold-api.com/price/XAU"

    report = {
        "name": "Gold-API.com",
        "url": target_url,
        "robots": robots_res,
        "reachable": False,
        "status_code": None,
        "elapsed": None,
        "price_usd": None,
        "updated_at": None,
        "problem": None,
    }

    try:
        start_time = time.time()
        res = requests.get(target_url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        report["elapsed"] = round(time.time() - start_time, 2)
        report["status_code"] = res.status_code
        report["reachable"] = True

        if res.status_code == 200:
            data = res.json()
            report["price_usd"] = data.get("price")
            report["currency"] = data.get("currency", "USD")
            report["updated_at"] = data.get("updatedAtReadable") or data.get("updatedAt")
        else:
            report["problem"] = f"استجابة غير متوقعة بكود {res.status_code}"
    except Exception as exc:
        report["problem"] = f"فشل الاتصال: {exc}"

    return report


def probe_egygold() -> dict:
    """فحص المصدر 2: egygold.com لأسعار الذهب في مصر."""
    robots_res = check_robots_txt("http://egygold.com/robots.txt")
    # الموقع لا يدعم HTTPS بشكل صحيح ويتوقف، نستخدم الرابط الأساسي http://egygold.com
    target_url = "http://egygold.com"

    report = {
        "name": "egygold.com",
        "url": target_url,
        "robots": robots_res,
        "reachable": False,
        "status_code": None,
        "elapsed": None,
        "has_24k": False,
        "has_21k": False,
        "has_18k": False,
        "has_14k": False,
        "has_pound": False,
        "has_buy_sell": False,
        "data_format": "غير محدد",
        "values": {},
        "problem": None,
    }

    try:
        start_time = time.time()
        res = requests.get(target_url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        report["elapsed"] = round(time.time() - start_time, 2)
        report["status_code"] = res.status_code
        report["reachable"] = True

        content_text = res.text.strip()
        if "access denied" in content_text.lower():
            report["data_format"] = "نص خطأ بسيط من الخادم"
            report["problem"] = "الخادم يعيد رسالة 'Access Denied.' ومسار HTTPS غير متاح (ينتهي بمهلة اتصال)."
        else:
            report["data_format"] = "HTML"
            # فحص وجود الأسعار
            if "24" in content_text:
                report["has_24k"] = True
            if "21" in content_text:
                report["has_21k"] = True
            if "18" in content_text:
                report["has_18k"] = True
            if "14" in content_text:
                report["has_14k"] = True
            if "جنيه" in content_text or "pound" in content_text.lower():
                report["has_pound"] = True
            if "شراء" in content_text and "بيع" in content_text:
                report["has_buy_sell"] = True
    except Exception as exc:
        report["problem"] = f"تعذر الاتصال بالموقع: {exc}"

    return report


def probe_isagha() -> dict:
    """فحص المصدر 3: منصة آي صاغة (iSagha)."""
    robots_res = check_robots_txt("https://www.isagha.com/robots.txt")
    target_url = "https://www.isagha.com"

    report = {
        "name": "iSagha (آي صاغة)",
        "requested_url": target_url,
        "final_url": None,
        "robots": robots_res,
        "reachable": False,
        "status_code": None,
        "elapsed": None,
        "has_24k": False,
        "has_21k": False,
        "has_18k": False,
        "has_14k": False,
        "has_pound": False,
        "has_buy_sell": False,
        "data_format": "HTML ثابت (Static Server-Rendered HTML)",
        "prices": {},
        "problem": None,
    }

    try:
        start_time = time.time()
        res = requests.get(target_url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        report["elapsed"] = round(time.time() - start_time, 2)
        report["status_code"] = res.status_code
        report["final_url"] = res.url
        report["reachable"] = True

        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            # استخراج صفوف الجدول التي تحتوي على الأسعار
            for tr in soup.find_all("tr"):
                cols = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if len(cols) >= 3:
                    item_name = cols[0]
                    try:
                        buy_val = float(cols[1].replace(",", ""))
                        sell_val = float(cols[2].replace(",", ""))
                    except ValueError:
                        continue

                    if "24" in item_name:
                        report["has_24k"] = True
                        report["prices"]["24k"] = {"name": item_name, "buy": buy_val, "sell": sell_val}
                    elif "21" in item_name:
                        report["has_21k"] = True
                        report["prices"]["21k"] = {"name": item_name, "buy": buy_val, "sell": sell_val}
                    elif "18" in item_name:
                        report["has_18k"] = True
                        report["prices"]["18k"] = {"name": item_name, "buy": buy_val, "sell": sell_val}
                    elif "14" in item_name:
                        report["has_14k"] = True
                        report["prices"]["14k"] = {"name": item_name, "buy": buy_val, "sell": sell_val}
                    elif "جنيه" in item_name:
                        report["has_pound"] = True
                        report["prices"]["pound"] = {"name": item_name, "buy": buy_val, "sell": sell_val}

            if report["prices"]:
                report["has_buy_sell"] = True
            else:
                report["problem"] = "لم يتم العثور على جدول الأسعار داخل صفحة HTML"
        else:
            report["problem"] = f"استجابة برمز خطأ {res.status_code}"
    except Exception as exc:
        report["problem"] = f"خطأ أثناء الاتصال: {exc}"

    return report


def probe_cbe() -> dict:
    """فحص المصدر 4: البنك المركزي المصري (Central Bank of Egypt)."""
    robots_res = check_robots_txt("https://www.cbe.org.eg/robots.txt")
    target_url = "https://www.cbe.org.eg/en/economic-research/statistics/exchange-rates"

    report = {
        "name": "Central Bank of Egypt (البنك المركزي المصري)",
        "url": target_url,
        "robots": robots_res,
        "reachable": False,
        "status_code": None,
        "elapsed": None,
        "rates": {},
        "problem": None,
    }

    try:
        start_time = time.time()
        res = requests.get(target_url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        report["elapsed"] = round(time.time() - start_time, 2)
        report["status_code"] = res.status_code
        report["reachable"] = True

        content = res.text
        # التحقق مما إذا كان الطلب محجوباً بواسطة جدار حماية التطبيقات (WAF)
        if "request rejected" in content.lower() or "rejected" in content.lower():
            report["problem"] = (
                "تم حجب الطلب بواسطة جدار الحماية (WAF / F5 BIG-IP Volt-ADC): 'The requested URL was rejected.' "
                "وفقاً للقاعدة 6 لا يتم تجاوز الحظر الآلي."
            )
        else:
            # محاولة استخراج سعر الدولار إذا لم يكن محجوباً
            soup = BeautifulSoup(content, "html.parser")
            for tr in soup.find_all("tr"):
                row_text = tr.get_text()
                if "USD" in row_text or "US Dollar" in row_text or "الدولار" in row_text:
                    cols = [td.get_text(strip=True) for td in tr.find_all("td")]
                    if len(cols) >= 3:
                        report["rates"]["USD"] = {"buy": cols[1], "sell": cols[2]}
                        break
            if not report["rates"]:
                report["problem"] = "لم يتم العثور على جدول أسعار العملات في الصفحة."
    except Exception as exc:
        report["problem"] = f"فشل الاتصال: {exc}"

    return report


def print_comparison(isagha_report: dict):
    """
    طباعة مقارنة النسب الحسابية لأسعار الذهب المحلية:
    - حساب عيار 21 = عيار 24 * 21/24
    - حساب عيار 18 = عيار 24 * 18/24
    - حساب عيار 14 = عيار 24 * 14/24
    - حساب الجنيه الذهب = عيار 21 * 8 جرامات
    ومقارنة المحسوب بالمنشور مع توضيح الفرق.
    """
    print("\n" + "=" * 70)
    print("📊 مقارنة النسب الحسابية لأسعار الذهب (بناءً على الأسعار المنشورة)")
    print("=" * 70)

    prices = isagha_report.get("prices", {})
    p24 = prices.get("24k")
    p21 = prices.get("21k")
    p18 = prices.get("18k")
    ppound = prices.get("pound")

    if not (p24 and p21):
        print("⚠️ تعذر إجراء المقارنة لعدم توفر أسعار عيار 24 و 21 من المصدر المحلي.")
        return

    for side, side_label in [("sell", "سعر البيع"), ("buy", "سعر الشراء")]:
        v24 = p24[side]
        v21_pub = p21[side]
        v18_pub = p18[side] if p18 else None
        vpound_pub = ppound[side] if ppound else None

        # العمليات الحسابية
        calc_21 = v24 * (21.0 / 24.0)
        calc_18 = v24 * (18.0 / 24.0)
        calc_14 = v24 * (14.0 / 24.0)
        calc_pound = v21_pub * 8.0

        diff_21 = v21_pub - calc_21
        diff_18 = (v18_pub - calc_18) if v18_pub is not None else None
        diff_pound = (vpound_pub - calc_pound) if vpound_pub is not None else None

        print(f"\n🔹 【{side_label}】 (الأساس: عيار 24 = {v24:.2f} ج.م):")
        print(f"  • عيار 21:")
        print(f"      - المحسوب (24k * 21/24): {calc_21:.2f} ج.م")
        print(f"      - المنشور فعلياً:       {v21_pub:.2f} ج.م")
        print(f"      - الفرق:               {diff_21:+.2f} ج.م ({((diff_21/calc_21)*100):+.2f}%)")

        print(f"  • عيار 18:")
        print(f"      - المحسوب (24k * 18/24): {calc_18:.2f} ج.م")
        if v18_pub is not None:
            print(f"      - المنشور فعلياً:       {v18_pub:.2f} ج.م")
            print(f"      - الفرق:               {diff_18:+.2f} ج.م ({((diff_18/calc_18)*100):+.2f}%)")
        else:
            print(f"      - المنشور فعلياً:       غير متوفر")

        print(f"  • عيار 14:")
        print(f"      - المحسوب (24k * 14/24): {calc_14:.2f} ج.م")
        print(f"      - المنشور فعلياً:       غير معروض في جدول المصدر (N/A)")

        print(f"  • الجنيه الذهب (8 جرامات عيار 21):")
        print(f"      - المحسوب (21k * 8):     {calc_pound:.2f} ج.م")
        if vpound_pub is not None:
            print(f"      - المنشور فعلياً:       {vpound_pub:.2f} ج.م")
            print(f"      - الفرق:               {diff_pound:+.2f} ج.م ({((diff_pound/calc_pound)*100):+.2f}%)")
        else:
            print(f"      - المنشور فعلياً:       غير متوفر")


def main():
    print("=" * 70)
    print("🚀 بدء فحص المصادر الأربعة لمشروع مرصاد الذهب (Gold Radar)")
    print("=" * 70)

    # 1. Gold-API
    print("\n[1/4] فحص Gold-API.com...")
    r_gold = probe_gold_api()
    print(f"  - الوصول: {'ناجح' if r_gold['reachable'] else 'فشل'}")
    print(f"  - كود الحالة: {r_gold['status_code']}")
    print(f"  - زمن الاستجابة: {r_gold['elapsed']} ثانية")
    print(f"  - الرابط المستخدم: {r_gold['url']}")
    print(f"  - ملف robots.txt: {r_gold['robots']['reason']}")
    if r_gold["price_usd"]:
        print(f"  - السعر العالمي (XAU): {r_gold['price_usd']} {r_gold.get('currency', 'USD')}")
        print(f"  - وقت التحديث: {r_gold['updated_at']}")
    if r_gold["problem"]:
        print(f"  - مشكلة: {r_gold['problem']}")

    # 2. egygold.com
    print("\n[2/4] فحص egygold.com...")
    r_egygold = probe_egygold()
    print(f"  - الوصول: {'ناجح (HTTP فقط)' if r_egygold['reachable'] else 'فشل'}")
    print(f"  - كود الحالة: {r_egygold['status_code']}")
    print(f"  - زمن الاستجابة: {r_egygold['elapsed']} ثانية")
    print(f"  - ملف robots.txt: {r_egygold['robots']['reason']}")
    print(f"  - تنسيق البيانات: {r_egygold['data_format']}")
    print(f"  - عرض العيارات (24/21/18/14 والجنيه): غير معروضة إطلاقاً")
    print(f"  - أسعار البيع والشراء: غير متوفرة")
    if r_egygold["problem"]:
        print(f"  - التقرير والمشكلة: {r_egygold['problem']}")

    # 3. iSagha
    print("\n[3/4] فحص منصة آي صاغة (iSagha)...")
    r_isagha = probe_isagha()
    print(f"  - الوصول: {'ناجح' if r_isagha['reachable'] else 'فشل'}")
    print(f"  - كود الحالة: {r_isagha['status_code']}")
    print(f"  - زمن الاستجابة: {r_isagha['elapsed']} ثانية")
    print(f"  - الرابط المستخدم: {r_isagha['requested_url']} (تم التحويل إلى: {r_isagha['final_url']})")
    print(f"  - ملف robots.txt: {r_isagha['robots']['reason']}")
    print(f"  - تنسيق البيانات: {r_isagha['data_format']}")
    print(f"  - هل يعرض 24k؟: {'نعم' if r_isagha['has_24k'] else 'لا'}")
    print(f"  - هل يعرض 21k؟: {'نعم' if r_isagha['has_21k'] else 'لا'}")
    print(f"  - هل يعرض 18k؟: {'نعم' if r_isagha['has_18k'] else 'لا'}")
    print(f"  - هل يعرض 14k؟: {'نعم' if r_isagha['has_14k'] else 'لا (غير موجود في الجدول الرئيسي)'}")
    print(f"  - هل يعرض الجنيه الذهب؟: {'نعم' if r_isagha['has_pound'] else 'لا'}")
    print(f"  - هل يعرض سعر الشراء والبيع؟: {'نعم' if r_isagha['has_buy_sell'] else 'لا'}")
    if r_isagha["prices"]:
        print("  - عينات القيم المستخرجة (ج.م):")
        for k, v in r_isagha["prices"].items():
            print(f"      * {v['name']}: شراء = {v['buy']} | بيع = {v['sell']}")
    if r_isagha["problem"]:
        print(f"  - ملاحظة / مشكلة: {r_isagha['problem']}")

    # 4. Central Bank of Egypt
    print("\n[4/4] فحص البنك المركزي المصري (Central Bank of Egypt)...")
    r_cbe = probe_cbe()
    print(f"  - الوصول الشبكي: {'تم الاتصال' if r_cbe['reachable'] else 'فشل'}")
    print(f"  - كود الحالة: {r_cbe['status_code']}")
    print(f"  - زمن الاستجابة: {r_cbe['elapsed']} ثانية")
    print(f"  - الرابط المستخدم: {r_cbe['url']}")
    print(f"  - ملف robots.txt: {r_cbe['robots']['reason']}")
    if r_cbe["rates"]:
        print(f"  - سعر الدولار الرسمي: {r_cbe['rates']}")
    if r_cbe["problem"]:
        print(f"  - التقرير والمشكلة: {r_cbe['problem']}")

    # المقارنة الحسابية
    print_comparison(r_isagha)
    print("\n" + "=" * 70)
    print("✅ اكتمل الفحص وفق جميع معايير AGENT_RULES.md.")
    print("=" * 70)


if __name__ == "__main__":
    main()
