"""
أداة الفحص الحي لطبقة المصادر (tools/check_sources_live.py).
لمشروع مرصاد الذهب (Gold Radar).

تنفذ طلباً واحداً حياً لكل مصدر من المصادر المعتمدة:
1. Gold-API (سعر أونصة الذهب عالمياً بالدولار)
2. آي صاغة (أسعار الذهب المحلية في مصر)
3. سعر صرف الدولار (المصدر الأساسي أو الاحتياطي)
وتطبع القيم المحللة باللغة العربية مع حساب السعر العادل والفجوة الحالية.
"""

import sys
from pathlib import Path

# ضبط ترميز المخرجات لدعم اللغة العربية
sys.stdout.reconfigure(encoding="utf-8")

# إضافة مجلد src إلى مسار الحزم
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gold_radar.calc import fair_price_24k, gap, market_status
from gold_radar.config import PRICE_SIDE
from gold_radar.sources.gold_api import fetch_ounce_price
from gold_radar.sources.isagha import fetch_local_prices
from gold_radar.sources.usd import get_usd_rate


def main():
    print("=" * 70)
    print("🛰️ فحص حي ومباشر لطبقة المصادر (مرصاد الذهب)")
    print("=" * 70)

    # 1. جلب سعر الأونصة العالمي
    print("\n[1/3] جلب سعر أونصة الذهب العالمي (Gold-API)...")
    try:
        ounce = fetch_ounce_price()
        print(f"  ✅ تم بنجاح:")
        print(f"      • السعر: {ounce.usd:.2f} دولار / أونصة")
        print(f"      • وقت الجلب (UTC): {ounce.fetched_at.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as exc:
        print(f"  ❌ خطأ في جلب سعر الأونصة: {exc}")
        ounce = None

    # 2. جلب أسعار الذهب المحلية من آي صاغة
    print("\n[2/3] جلب أسعار الذهب المحلية من منصة آي صاغة...")
    try:
        local = fetch_local_prices()
        print(f"  ✅ تم بنجاح:")
        print(f"      • عيار 24: شراء = {local.buy_24k:.2f} ج.م | بيع = {local.sell_24k:.2f} ج.م")
        print(f"      • عيار 21: شراء = {local.buy_21k:.2f} ج.م | بيع = {local.sell_21k:.2f} ج.م")
        print(f"      • عيار 18: شراء = {local.buy_18k:.2f} ج.م | بيع = {local.sell_18k:.2f} ج.م")
        print(f"      • الجنيه الذهب: شراء = {local.buy_pound:.2f} ج.م | بيع = {local.sell_pound:.2f} ج.م")
        print(f"      • وقت الجلب (UTC): {local.fetched_at.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as exc:
        print(f"  ❌ خطأ في جلب أسعار آي صاغة: {exc}")
        local = None

    # 3. جلب سعر صرف الدولار
    print("\n[3/3] جلب سعر صرف الدولار مقابل الجنيه (USD/EGP)...")
    try:
        usd = get_usd_rate()
        print(f"  ✅ تم بنجاح:")
        print(f"      • المصدر المستخدم: {usd.source_name}")
        print(f"      • السعر: {usd.rate:.4f} ج.م")
        print(f"      • وقت الجلب (UTC): {usd.fetched_at.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as exc:
        print(f"  ❌ خطأ في جلب سعر الدولار: {exc}")
        usd = None

    # 4. الحسابات الفورية إذا اكتملت البيانات
    if ounce and local and usd:
        print("\n" + "=" * 70)
        print("📊 ملخص الحسابات اللحظية للسوق:")
        print("=" * 70)

        # حساب السعر العادل
        fair_24k = fair_price_24k(ounce.usd, usd.rate)

        # تحديد السعر المعتمد بناءً على PRICE_SIDE في الإعدادات
        chosen_local_price = local.sell_24k if PRICE_SIDE == "sell" else local.buy_24k
        side_label = "سعر البيع" if PRICE_SIDE == "sell" else "سعر الشراء"

        gap_egp, gap_pct = gap(chosen_local_price, fair_24k)
        status = market_status(gap_pct)

        status_arabic = {
            "balanced": "متوازن مع السعر العالمي (ضمن ±1%)",
            "higher": "أعلى من السعر العالمي (علاوة سعرية)",
            "lower": "أقل من السعر العالمي (خصم)",
        }.get(status, status)

        print(f"  • نوع السعر المعتمد: {side_label} لعيار 24")
        print(f"  • السعر المحلي لعيار 24: {chosen_local_price:.2f} ج.م")
        print(f"  • السعر العادل العالمي:  {fair_24k:.2f} ج.م")
        print(f"  • الفجوة السعرية:        {gap_egp:+.2f} ج.م ({gap_pct:+.2f}%)")
        print(f"  • حالة السوق:            {status_arabic}")
        print("=" * 70)
    else:
        print("\n⚠️ لم تكتمل البيانات لإجراء الحسابات الفورية.")


if __name__ == "__main__":
    main()
