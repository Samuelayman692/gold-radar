"""
معاينة نص رسالة التنبيه (tools/preview_message.py).
لمشروع مرصاد الذهب (Gold Radar).

تقوم ببناء رسالة نموذجية بأرقام واقعية ثابتة (بدون أي اتصال شبكي)
وتطبعها في الطرفية لمعاينتها والتأكد من شكلها النهائي قبل إرسالها إلى تيليجرام.
"""

from datetime import datetime, timezone
import sys
from pathlib import Path

# ضبط ترميز المخرجات لدعم اللغة العربية
sys.stdout.reconfigure(encoding="utf-8")

# إضافة مجلد src لمسار الحزم
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gold_radar.calc import derived_karat_price, fair_price_24k, gap, gold_pound_price, market_status
from gold_radar.message import MessageData, build_message


def main():
    print("=" * 60)
    print("📱 معاينة رسالة تيليجرام (Telegram Alert Message Preview)")
    print("=" * 60)

    # أرقام نموذجية ثابتة تحاكي واقع السوق اللحظي
    p24 = 6588.50
    p21 = 5765.00
    p18 = 4941.50
    p14 = derived_karat_price(p24, 14)  # محسوب من عيار 24
    pound = gold_pound_price(p21)       # محسوب من عيار 21
    ounce_usd = 3732.15
    usd_egp = 53.74

    # الحسابات
    fair_24 = fair_price_24k(ounce_usd, usd_egp)
    gap_val, gap_percent = gap(p24, fair_24)
    status_key = market_status(gap_percent)

    # تجهيز كائن البيانات
    data = MessageData(
        price_24k=p24,
        price_21k=p21,
        price_18k=p18,
        price_14k=p14,
        gold_pound=pound,
        ounce_usd=ounce_usd,
        usd_egp=usd_egp,
        fair_24k=fair_24,
        gap_egp=gap_val,
        gap_pct=gap_percent,
        status=status_key,
        updated_at_utc=datetime.now(timezone.utc),
    )

    # بناء الرسالة
    message_text = build_message(data)

    print("\n--- [بداية الرسالة] ---")
    print(message_text)
    print("--- [نهاية الرسالة] ---\n")
    print("=" * 60)


if __name__ == "__main__":
    main()
