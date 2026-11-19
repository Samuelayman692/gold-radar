"""
استخراج معرف المحادثة تلقائياً (tools/get_chat_id.py).
لمشروع مرصاد الذهب (Gold Radar).

يقرأ TELEGRAM_BOT_TOKEN من ملف .env المحلي عبر python-dotenv،
ويستدعي getUpdates للبحث عن آخر رسالة أرسلتها للبوت، ثم يستخرج chat_id
ويحفظه تلقائياً في ملف .env دون طباعة التوكن أو كامل المعرف حفاظاً على السرية.
"""

import os
import sys
from pathlib import Path
import requests
from dotenv import load_dotenv

# ضبط ترميز المخرجات لدعم اللغة العربية
sys.stdout.reconfigure(encoding="utf-8")

# إضافة مجلد src لمسار الحزم
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from gold_radar.config import USER_AGENT


def update_env_file(env_path: Path, key: str, value: str) -> None:
    """إضافة أو تحديث متغير في ملف .env بأمان."""
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    key_found = False
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}=") or line.strip().startswith(f"{key} ="):
            new_lines.append(f"{key}={value}")
            key_found = True
        else:
            new_lines.append(line)

    if not key_found:
        new_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def main():
    print("=" * 60)
    print("🔍 البحث التلقائي عن معرف محادثة تيليجرام (Chat ID)")
    print("=" * 60)

    # تحميل ملف .env
    root_dir = Path(__file__).resolve().parent.parent
    env_file = root_dir / ".env"
    venv_env_file = root_dir / ".venv" / ".env"

    load_dotenv(env_file)
    if not os.environ.get("TELEGRAM_BOT_TOKEN") and venv_env_file.exists():
        load_dotenv(venv_env_file)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("❌ لم يتم العثور على TELEGRAM_BOT_TOKEN في ملف .env")
        print("يرجى التأكد من إضافة السطر التالي داخل ملف .env:")
        print("TELEGRAM_BOT_TOKEN=رمز_البوت_الخاص_بك")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    headers = {"User-Agent": USER_AGENT}

    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            print(f"❌ استجابة غير ناجحة من خوادم تيليجرام (كود {res.status_code})")
            sys.exit(1)

        data = res.json()
        updates = data.get("result", [])
    except Exception:
        print("❌ تعذر الاتصال بخوادم تيليجرام للتحقق من الرسائل الواردة.")
        sys.exit(1)

    # البحث عن معرف المحادثة من آخر رسالة خاصة
    chat_id = None
    for update in reversed(updates):
        msg = update.get("message") or update.get("edited_message") or update.get("channel_post")
        if msg and "chat" in msg:
            chat_info = msg["chat"]
            chat_id = chat_info.get("id")
            break

    if not chat_id:
        print("\n⚠️ لم يتم العثور على أي رسائل واردة للبوت بعد.")
        print("💡 الخطوات المطلوبة:")
        print("1. افتح تطبيق تيليجرام وابحث عن البوت الذي أنشأته.")
        print("2. اضغط على 'Start' أو أرسل له أي رسالة (مثلاً: /start).")
        print("3. أعد تشغيل هذا السكربت مرة أخرى وسيتعرف على محادثتك فوراً.\n")
        sys.exit(0)

    # حفظ chat_id في ملف .env
    chat_id_str = str(chat_id)
    update_env_file(env_file, "TELEGRAM_CHAT_ID", chat_id_str)
    if venv_env_file.exists():
        update_env_file(venv_env_file, "TELEGRAM_CHAT_ID", chat_id_str)

    # طباعة آخر 3 أرقام فقط للحفاظ على السرية
    masked_id = f"...{chat_id_str[-3:]}" if len(chat_id_str) >= 3 else "..."
    print(f"\n✅ نجاح! تم العثور على المحادثة وحفظ المعرف في ملف .env بنجاح (ينتهي بالرقم: {masked_id})")
    print("=" * 60)


if __name__ == "__main__":
    main()
