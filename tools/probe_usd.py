"""
أداة فحص مصادر سعر صرف الدولار مقابل الجنيه (tools/probe_usd.py)
لمشروع مرصاد الذهب (Gold Radar)

تفحص مصادر USD/EGP بدون أي مفاتيح API وبطلب واحد لكل مصدر:
1. open.er-api.com (خدمة مجانية بدون مفتاح)
2. fawazahmed0 currency-api عبر شبكة jsDelivr
3. market.isagha.com (التحقق من وجود سعر الدولار في الصفحة المستخدمة للذهب)
4. fxratesapi.com (مصدر مجاني إضافي بدون مفتاح موثق رسمياً)

في النهاية: حساب ومقارنة "دولار الصاغة الضمني" المشتق من سعر الذهب لحظياً
(Implied Rate = سعر عيار 24 × 31.1035 / سعر أونصة الذهب العالمي XAU).
"""

import sys
import time
import requests
from bs4 import BeautifulSoup

# ضبط ترميز المخرجات للغة العربية
sys.stdout.reconfigure(encoding="utf-8")

# الثوابت المتبعة في القواعد
USER_AGENT = "GoldRadar/0.1"
TIMEOUT_SECONDS = 15
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json,text/html,*/*;q=0.9",
    "Accept-Language": "ar,en;q=0.8",
}
TROY_OUNCE_GRAMS = 31.1035


def check_robots_txt(robots_url: str) -> dict:
    """فحص ملف robots.txt بأدب للتأكد من عدم وجود منع للزحف."""
    try:
        res = requests.get(robots_url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        if res.status_code == 200:
            content = res.text.lower()
            if "disallow: /" in content and "disallow: /\n" in content:
                return {"allowed": False, "note": "يمنع الزحف الشامل (Disallow: /)"}
            return {"allowed": True, "note": "مسموح بالقراءة الآلية"}
        elif res.status_code == 404:
            return {"allowed": True, "note": "لا يوجد ملف robots.txt (404) - لا توجد قيود معلنة"}
        else:
            return {"allowed": True, "note": f"كود الاستجابة {res.status_code}"}
    except Exception as exc:
        return {"allowed": False, "note": f"تعذر الاتصال بملف robots: {exc}"}


def probe_open_er_api() -> dict:
    """فحص المصدر 1: open.er-api.com"""
    robots_res = check_robots_txt("https://open.er-api.com/robots.txt")
    url = "https://open.er-api.com/v6/latest/USD"

    report = {
        "name": "Open Exchange Rates API (open.er-api.com)",
        "url": url,
        "robots": robots_res,
        "reachable": False,
        "status_code": None,
        "elapsed": None,
        "rate_egp": None,
        "freshness": None,
        "terms_summary": "مسموح للاستخدام الشخصي والتجاري بشرط ذكر المصدر (Attribution / Backlink) مع منع إعادة بيع البيانات الخام.",
        "problem": None,
    }

    try:
        start_time = time.time()
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        report["elapsed"] = round(time.time() - start_time, 2)
        report["status_code"] = res.status_code
        report["reachable"] = True

        if res.status_code == 200:
            data = res.json()
            rates = data.get("rates", {})
            report["rate_egp"] = rates.get("EGP")
            report["freshness"] = data.get("time_last_update_utc")
        else:
            report["problem"] = f"استجابة غير متوقعة: كود {res.status_code}"
    except Exception as exc:
        report["problem"] = f"فشل الاتصال: {exc}"

    return report


def probe_fawazahmed0_api() -> dict:
    """فحص المصدر 2: fawazahmed0 currency-api عبر jsDelivr"""
    robots_res = check_robots_txt("https://cdn.jsdelivr.net/robots.txt")
    url = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json"

    report = {
        "name": "Fawaz Ahmed Currency API (عبر jsDelivr CDN)",
        "url": url,
        "robots": robots_res,
        "reachable": False,
        "status_code": None,
        "elapsed": None,
        "rate_egp": None,
        "freshness": None,
        "terms_summary": "مشروع مفتوح المصدر (Public Domain / MIT)، متاح مجاناً بالكامل للاستخدام الشخصي والتجاري وبدون قيود أو مفاتيح.",
        "problem": None,
    }

    try:
        start_time = time.time()
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        report["elapsed"] = round(time.time() - start_time, 2)
        report["status_code"] = res.status_code
        report["reachable"] = True

        if res.status_code == 200:
            data = res.json()
            report["rate_egp"] = data.get("usd", {}).get("egp")
            report["freshness"] = data.get("date")
        else:
            report["problem"] = f"استجابة غير متوقعة: كود {res.status_code}"
    except Exception as exc:
        report["problem"] = f"فشل الاتصال: {exc}"

    return report


def probe_isagha_usd() -> dict:
    """فحص المصدر 3: منصة آي صاغة للتأكد من وجود سعر صرف USD/EGP في الصفحة"""
    robots_res = check_robots_txt("https://www.isagha.com/robots.txt")
    url = "https://www.isagha.com"

    report = {
        "name": "منصة آي صاغة (market.isagha.com)",
        "url": url,
        "robots": robots_res,
        "reachable": False,
        "status_code": None,
        "elapsed": None,
        "rate_egp": None,
        "freshness": None,
        "terms_summary": "موقع إلكتروني عام مخصص لأسعار المشغولات والسبائك الذهبية والفضية.",
        "problem": None,
    }

    try:
        start_time = time.time()
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        report["elapsed"] = round(time.time() - start_time, 2)
        report["status_code"] = res.status_code
        report["reachable"] = True

        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            usd_found = False
            # فحص الجداول للبحث عن سعر صرف للدولار
            for tr in soup.find_all("tr"):
                txt = tr.get_text()
                if "دولار" in txt or "USD" in txt:
                    usd_found = True
                    break

            if not usd_found:
                report["problem"] = "الصفحة تعرض أسعار الذهب والفضة فقط، ولا تعرض جدولاً رسمياً لسعر صرف USD/EGP."
        else:
            report["problem"] = f"كود الاستجابة: {res.status_code}"
    except Exception as exc:
        report["problem"] = f"فشل الاتصال: {exc}"

    return report


def probe_fxratesapi() -> dict:
    """فحص المصدر 4 (إضافي موثق مجاناً وبدون مفتاح): fxratesapi.com"""
    robots_res = check_robots_txt("https://api.fxratesapi.com/robots.txt")
    url = "https://api.fxratesapi.com/latest"

    report = {
        "name": "FXRatesAPI (api.fxratesapi.com)",
        "url": url,
        "robots": robots_res,
        "reachable": False,
        "status_code": None,
        "elapsed": None,
        "rate_egp": None,
        "freshness": None,
        "terms_summary": "واجهة برمجة تطبيقات تجارية تتيح نقطة نهاية مجانية مفتوحة بدون مفتاح للأسعار اللحظية مع شروط استخدام عامة.",
        "problem": None,
    }

    try:
        start_time = time.time()
        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        report["elapsed"] = round(time.time() - start_time, 2)
        report["status_code"] = res.status_code
        report["reachable"] = True

        if res.status_code == 200:
            data = res.json()
            report["rate_egp"] = data.get("rates", {}).get("EGP")
            report["freshness"] = data.get("date")
        else:
            report["problem"] = f"استجابة غير متوقعة: كود {res.status_code}"
    except Exception as exc:
        report["problem"] = f"فشل الاتصال: {exc}"

    return report


def fetch_live_gold_for_implied_rate() -> tuple[float | None, float | None, float | None]:
    """جلب سعر الذهب 24k وسعر الأونصة العالمي بحركة واحدة لكل منهما لحساب الدولار الضمني."""
    xau_usd = None
    p24_buy = None
    p24_sell = None

    # 1. سعر الأونصة العالمي بالدولار من Gold-API
    try:
        r_gold = requests.get("https://api.gold-api.com/price/XAU", headers=HEADERS, timeout=TIMEOUT_SECONDS)
        if r_gold.status_code == 200:
            xau_usd = float(r_gold.json().get("price", 0))
    except Exception:
        pass

    # 2. سعر عيار 24 المحلي من آي صاغة
    try:
        r_isagha = requests.get("https://www.isagha.com", headers=HEADERS, timeout=TIMEOUT_SECONDS)
        if r_isagha.status_code == 200:
            soup = BeautifulSoup(r_isagha.text, "html.parser")
            for tr in soup.find_all("tr"):
                cols = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if len(cols) >= 3 and "24" in cols[0]:
                    p24_buy = float(cols[1].replace(",", ""))
                    p24_sell = float(cols[2].replace(",", ""))
                    break
    except Exception:
        pass

    return xau_usd, p24_buy, p24_sell


def print_comparison(usd_sources: list[dict], xau_usd: float, p24_buy: float, p24_sell: float):
    """
    طباعة مقارنة سعر صرف الدولار الفعلي مقابل الدولار الضمني المشتق من الذهب:
    Implied Rate = (سعر عيار 24 × 31.1035) / سعر أونصة الذهب العالمي
    """
    print("\n" + "=" * 75)
    print("⚖️ مقارنة أسعار الصرف مع 'سعر الدولار الضمني في سوق الذهب' (دولار الصاغة)")
    print("=" * 75)

    if not (xau_usd and p24_buy and p24_sell):
        print("⚠️ تعذر حساب الدولار الضمني لعدم اكتمال بيانات سعر الذهب أو الأونصة اللحظية.")
        return

    # حساب الدولار الضمني للشراء والبيع
    implied_buy = (p24_buy * TROY_OUNCE_GRAMS) / xau_usd
    implied_sell = (p24_sell * TROY_OUNCE_GRAMS) / xau_usd

    print(f"🔹 البيانات اللحظية المستخدمة:")
    print(f"   • سعر أونصة الذهب عالمياً (Gold-API): {xau_usd:.2f} دولار")
    print(f"   • سعر عيار 24 محلياً (iSagha): شراء = {p24_buy:.2f} ج.م | بيع = {p24_sell:.2f} ج.م")
    print(f"   • وزن الأونصة الترويسية: {TROY_OUNCE_GRAMS} جرام")
    print(f"   👉 الدولار الضمني (شراء): {implied_buy:.3f} ج.م")
    print(f"   👉 الدولار الضمني (بيع):  {implied_sell:.3f} ج.م")
    print("-" * 75)

    print(f"{'المصدر':<30} | {'السعر (ج.م)':<12} | {'فارق الشراء (%)':<16} | {'فارق البيع (%)':<16}")
    print("-" * 75)

    for src in usd_sources:
        rate = src.get("rate_egp")
        name = src.get("name")
        if rate:
            diff_buy = ((rate - implied_buy) / implied_buy) * 100
            diff_sell = ((rate - implied_sell) / implied_sell) * 100
            print(f"{name[:28]:<30} | {rate:<12.4f} | {diff_buy:+15.2f}% | {diff_sell:+15.2f}%")
        else:
            print(f"{name[:28]:<30} | {'غير متوفر':<12} | {'-':<16} | {'-':<16}")


def main():
    print("=" * 75)
    print("💵 فحص مصادر سعر صرف الدولار مقابل الجنيه (USD/EGP)")
    print("=" * 75)

    sources_reports = []

    # 1. open.er-api.com
    print("\n[1/4] فحص open.er-api.com...")
    r1 = probe_open_er_api()
    sources_reports.append(r1)
    print(f"  • الوصول: {'ناجح' if r1['reachable'] else 'فشل'}")
    print(f"  • كود الحالة: {r1['status_code']} | زمن الاستجابة: {r1['elapsed']} ثانية")
    print(f"  • الرابط الدقيق: {r1['url']}")
    print(f"  • سعر USD/EGP: {r1['rate_egp']} ج.م")
    print(f"  • حداثة البيانات: {r1['freshness']}")
    print(f"  • ملف robots.txt: {r1['robots']['note']}")
    print(f"  • الشروط والاستخدام التجاري: {r1['terms_summary']}")
    if r1["problem"]:
        print(f"  • المشاكل والقيود: {r1['problem']}")

    # 2. fawazahmed0 currency-api
    print("\n[2/4] فحص Fawaz Ahmed Currency API (jsDelivr)...")
    r2 = probe_fawazahmed0_api()
    sources_reports.append(r2)
    print(f"  • الوصول: {'ناجح' if r2['reachable'] else 'فشل'}")
    print(f"  • كود الحالة: {r2['status_code']} | زمن الاستجابة: {r2['elapsed']} ثانية")
    print(f"  • الرابط الدقيق: {r2['url']}")
    print(f"  • سعر USD/EGP: {r2['rate_egp']} ج.م")
    print(f"  • حداثة البيانات: {r2['freshness']}")
    print(f"  • ملف robots.txt: {r2['robots']['note']}")
    print(f"  • الشروط والاستخدام التجاري: {r2['terms_summary']}")
    if r2["problem"]:
        print(f"  • المشاكل والقيود: {r2['problem']}")

    # 3. market.isagha.com
    print("\n[3/4] فحص صفحة منصة آي صاغة (market.isagha.com)...")
    r3 = probe_isagha_usd()
    sources_reports.append(r3)
    print(f"  • الوصول: {'ناجح' if r3['reachable'] else 'فشل'}")
    print(f"  • كود الحالة: {r3['status_code']} | زمن الاستجابة: {r3['elapsed']} ثانية")
    print(f"  • الرابط الدقيق: {r3['url']}")
    print(f"  • سعر USD/EGP في الصفحة: {'غير معروض' if not r3['rate_egp'] else r3['rate_egp']}")
    print(f"  • ملف robots.txt: {r3['robots']['note']}")
    print(f"  • النتيجة والتقرير: {r3['problem'] or 'تم العثور على السعر'}")

    # 4. fxratesapi.com
    print("\n[4/4] فحص FXRatesAPI (مصدر إضافي مجاني بدون مفتاح)...")
    r4 = probe_fxratesapi()
    sources_reports.append(r4)
    print(f"  • الوصول: {'ناجح' if r4['reachable'] else 'فشل'}")
    print(f"  • كود الحالة: {r4['status_code']} | زمن الاستجابة: {r4['elapsed']} ثانية")
    print(f"  • الرابط الدقيق: {r4['url']}")
    print(f"  • سعر USD/EGP: {r4['rate_egp']} ج.م")
    print(f"  • حداثة البيانات: {r4['freshness']}")
    print(f"  • ملف robots.txt: {r4['robots']['note']}")
    print(f"  • الشروط والاستخدام التجاري: {r4['terms_summary']}")
    if r4["problem"]:
        print(f"  • المشاكل والقيود: {r4['problem']}")

    # جلب بيانات الذهب لحساب الدولار الضمني
    print("\n⏳ جلب سعر الذهب اللحظي لحساب الدولار الضمني (Implied Rate)...")
    xau_usd, p24_buy, p24_sell = fetch_live_gold_for_implied_rate()

    # طباعة المقارنة
    print_comparison(sources_reports, xau_usd, p24_buy, p24_sell)
    print("\n" + "=" * 75)
    print("✅ اكتمل فحص مصادر سعر الصرف وحساب الدولار الضمني بنجاح.")
    print("=" * 75)


if __name__ == "__main__":
    main()
