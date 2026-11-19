"""
تشغيل منظومة مرصاد الذهب محلياً (tools/run_local.py).
لمشروع مرصاد الذهب (Gold Radar).

يقوم بتحميل المتغيرات السرية من ملف .env المحلي بأمان،
ثم يستدعي الدالة الرئيسية main() مع تمرير المعاملات (مثل --dry-run).
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ضبط ترميز المخرجات لدعم اللغة العربية
sys.stdout.reconfigure(encoding="utf-8")

# إضافة مجلد src لمسار الحزم
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))

# تحميل ملف .env
env_file = root_dir / ".env"
venv_env_file = root_dir / ".venv" / ".env"

load_dotenv(env_file)
if not os.environ.get("GOOGLE_SHEET_ID") and venv_env_file.exists():
    load_dotenv(venv_env_file)

from gold_radar.main import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
