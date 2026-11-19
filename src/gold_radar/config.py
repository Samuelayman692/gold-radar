"""
إعدادات وثوابت مشروع مرصاد الذهب (config.py).
جميع الأرقام والقيم القابلة للضبط مجمعة هنا وفق القاعدة رقم 4 في AGENT_RULES.md.
"""

# نسبة حركة السعر المطلوبة لإرسال تنبيه (0.25%)
ALERT_THRESHOLD_PCT: float = 0.25

# حد الفجوة السعرية لاعتبار السوق متوازناً (±1.0%)
BALANCED_GAP_PCT: float = 1.0

# عدد جرامات أونصة الذهب الترويسية عالمياً
GRAMS_PER_TROY_OUNCE: float = 31.1035

# نقاء ونسب العيارات الذهبية الشائعة
KARAT_PURITY: dict[int, float] = {
    24: 24.0 / 24.0,
    21: 21.0 / 24.0,
    18: 18.0 / 24.0,
    14: 14.0 / 24.0,
}

# وزن الجنيه الذهب الرسمي من عيار 21 (جرامات)
GOLD_POUND_GRAMS_21K: float = 8.0

# نوع السعر المعتمد للتنبيه والفجوة السعرية ("sell" للبيع أو "buy" للشراء)
PRICE_SIDE: str = "sell"
if PRICE_SIDE not in ("sell", "buy"):
    raise ValueError(f"PRICE_SIDE must be either 'sell' or 'buy', got '{PRICE_SIDE}'")

# إعدادات رسائل التنبيه
MESSAGE_TIMEZONE: str = "Africa/Cairo"
USD_LABEL: str = "سعر الدولار (المركزي)"
CALCULATED_TAG: str = "محسوب"

# إعدادات كشف القفزات المفاجئة والمشبوهة في الأسعار
MAX_JUMP_PCT: float = 5.0                     # القفزة المشبوهة (أكبر من 5%)
SUSPICIOUS_CONFIRM_RUNS: int = 2              # عدد مرات التأكيد للقفزة المشبوهة
SUSPICIOUS_CONFIRM_TOLERANCE_PCT: float = 1.0  # نسبة التسامح لاستقرار السعر المشبوه (1.0%)

# إعدادات تيليجرام
TELEGRAM_TIMEOUT_SECONDS: int = 15
TELEGRAM_MAX_RETRIES: int = 3
TELEGRAM_MAX_RETRY_AFTER_SECONDS: int = 30
TELEGRAM_MAX_MESSAGE_LENGTH: int = 4096

# إعدادات جداول جوجل (Google Sheets)
HISTORY_SHEET_NAME: str = "التاريخ"
STATE_SHEET_NAME: str = "الحالة"
HISTORY_EVERY_RUN: bool = True  # تسجيل كل دورة في التاريخ (إذا كانت False يسجل فقط عند وجود حدث أو تنبيه)
SHEETS_TIMEOUT_SECONDS: int = 20
SHEETS_MAX_RETRIES: int = 3

# إعدادات الشبكة ومكافحة الأخطاء
NETWORK_TIMEOUT_SECONDS: int = 15
MAX_RETRIES: int = 3
RETRY_BACKOFF_FACTOR: float = 0.5
USER_AGENT: str = "GoldRadar/0.1"

# الحد الأقصى لعمر البيانات المقبولة
MAX_OUNCE_AGE_MINUTES: int = 30  # أقصى عمر لسعر الأونصة العالمي (30 دقيقة)
MAX_USD_AGE_DAYS: int = 2        # أقصى عمر لسعر صرف الدولار (يومان)

# حدود الأمان المنطقية للتحقق من صحة البيانات (Plausible ranges)
OUNCE_USD_MIN: float = 1000.0   # أدنى سعر منطقي لأونصة الذهب بالدولار
OUNCE_USD_MAX: float = 10000.0  # أقصى سعر منطقي لأونصة الذهب بالدولار

USD_EGP_MIN: float = 20.0       # أدنى سعر منطقي لصرف الدولار بالجنيه
USD_EGP_MAX: float = 150.0      # أقصى سعر منطقي لصرف الدولار بالجنيه

PRICE_24K_MIN: float = 1000.0   # أدنى سعر منطقي لجرام 24 بالجنيه
PRICE_24K_MAX: float = 25000.0  # أقصى سعر منطقي لجرام 24 بالجنيه
