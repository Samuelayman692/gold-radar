"""
إرسال رسالة اختبار لتيليجرام (tools/send_test_message.py).
لمشروع مرصاد الذهب (Gold Radar).

يقرأ المتغيرين (TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID) من ملف .env المحلي
ويرسل نصاً تجريبياً ثابتاً: "اختبار مرصاد الذهب ✅" للتأكد من وصول الرسائل لحسابك.
أمان تام: لا يطبع التوكن أو معرف المحادثة إطلاقاً في المخرجات أو الأخطاء.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ضبط ترميز المخرجات لدعم اللغة العربية
sys.stdout.reconfigure(encoding="utf-8")

# إضافة مجلد src لمسار الحزم
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gold_radar.telegram_client import send_message


def main():
    print("=" * 60)
    print("🚀 إرسال رسالة اختبار إلى تيليجرام")
    print("=" * 60)

    # تحميل المتغيرات من .env
    root_dir = Path(__file__).resolve().parent.parent
    load_dotenv(root_dir / ".env")
    if not os.environ.get("TELEGRAM_CHAT_ID") and (root_dir / ".venv" / ".env").exists():
        load_dotenv(root_dir / ".venv" / ".env")

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not token:
        print("❌ لم يتم العثور على TELEGRAM_BOT_TOKEN في ملف .env")
        sys.exit(1)

    if not chat_id:
        print("❌ لم يتم العثور على TELEGRAM_CHAT_ID في ملف .env")
        print("يرجى تشغيل أداة استخراج المعرف أولاً: python tools/get_chat_id.py")
        sys.exit(1)

    test_text = "اختبار مرصاد الذهب ✅"

    try:
        send_message(text=test_text, token=token, chat_id=chat_id)
        print("\n✅ تم إرسال رسالة الاختبار بنجاح!")
        print("📱 يرجى تفقد تطبيق تيليجرام الآن للتأكد من وصول الرسالة.")
        print("=" * 60)
    except Exception as exc:
        print(f"\n❌ فشل إرسال رسالة الاختبار: {exc}")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
