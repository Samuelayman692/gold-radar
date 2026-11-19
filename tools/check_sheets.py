"""
أداة فحص الاتصال بجداول جوجل (tools/check_sheets.py).
لمشروع مرصاد الذهب (Gold Radar).

يقرأ المتغيرات من .env المحلي، ويتأكد من وجود الأوراق المطلوبة ('الحالة' و 'التاريخ')،
ويختبر كتابة وقراءة ومطابقة الحالة، ثم يعيد ضبط ورقة الحالة إلى الوضع الافتراضي (فارغة للدورة الأولى)،
دون إضافة أي صف لورقة التاريخ.
أمان تام: لا يطبع أي أسرار أو معرفات إطلاقاً.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ضبط ترميز المخرجات لدعم اللغة العربية
sys.stdout.reconfigure(encoding="utf-8")

# إضافة مجلد src لمسار الحزم
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gold_radar.alert_logic import AlertState
from gold_radar.sheets_store import ensure_sheets, open_store, read_state, write_state


def main():
    print("=" * 65)
    print("📊 فحص الاتصال وتخزين البيانات في جداول جوجل (Google Sheets)")
    print("=" * 65)

    root_dir = Path(__file__).resolve().parent.parent
    load_dotenv(root_dir / ".env")
    if not os.environ.get("GOOGLE_SHEET_ID") and (root_dir / ".venv" / ".env").exists():
        load_dotenv(root_dir / ".venv" / ".env")

    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "").strip()

    if not sa_json:
        print("❌ لم يتم العثور على GOOGLE_SERVICE_ACCOUNT_JSON في ملف .env")
        sys.exit(1)

    if not sheet_id:
        print("❌ لم يتم العثور على GOOGLE_SHEET_ID في ملف .env")
        sys.exit(1)

    try:
        # 1. فتح الاتصال بالمصنف
        print("[1/5] جاري الاتصال بحساب الخدمة وفتح الجدول...")
        handle = open_store(sa_json, sheet_id)
        print("  ✅ تم الاتصال بنجاح وفتح المصنف.")

        # 2. التأكد من وجود الأوراق وإنشائها إذا لم تكن موجودة
        print("[2/5] التحقق من وجود الأوراق المعتمدة ('الحالة' و 'التاريخ')...")
        ensure_sheets(handle)
        print("  ✅ الأوراق جاهزة بالترويسات المعتمدة.")

        # 3. اختبار كتابة حالة تجريبية
        print("[3/5] كتابة حالة اختبار في ورقة 'الحالة'...")
        test_state = AlertState(
            last_alert_price=6611.50,
            last_seen_price=6615.00,
            suspicious_count=1,
            last_suspicious_price=6700.00,
        )
        write_state(handle, test_state)
        print("  ✅ تمت كتابة الحالة التجريبية.")

        # 4. قراءة الحالة ومطابقتها
        print("[4/5] إعادة قراءة الحالة من الجدول ومطابقتها...")
        read_back = read_state(handle)
        if read_back != test_state:
            raise RuntimeError(
                f"عدم تطابق في قراءة الحالة: المتوقع {test_state}، المقروء {read_back}"
            )
        print("  ✅ تمت المطابقة بنجاح تام (100%).")

        # 5. تصفير ورقة الحالة للدورة الأولى الحقيقية
        print("[5/5] إعادة ضبط ورقة الحالة لتكون جاهزة للدورة الأولى...")
        empty_state = AlertState(
            last_alert_price=None,
            last_seen_price=None,
            suspicious_count=0,
            last_suspicious_price=None,
        )
        write_state(handle, empty_state)

        # التحقق من أن القراءة تعطي None للدورة الأولى
        verified_empty = read_state(handle)
        if verified_empty.last_alert_price is not None:
            raise RuntimeError("فشل تصفير حالة التنبيهات.")
        print("  ✅ تم تصفير الحالة بنجاح (جاهزة للدورة الأولى).")

        print("\n" + "=" * 65)
        print("✅ اكتمل فحص جداول جوجل بنجاح تام وبدون أي أخطاء!")
        print("=" * 65)

    except Exception as exc:
        print(f"\n❌ حدث خطأ أثناء فحص جداول جوجل: {exc}")
        print("=" * 65)
        sys.exit(1)


if __name__ == "__main__":
    main()
