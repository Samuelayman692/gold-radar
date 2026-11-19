"""
المنسق الرئيسي لمنظومة مرصاد الذهب (src/gold_radar/main.py).
لمشروع مرصاد الذهب (Gold Radar).

يقوم بالتنسيق الكامل للدورة:
1. قراءة الحالة السابقة من جداول جوجل.
2. جلب الأسعار الحية (الأونصة، السوق المحلي، سعر الصرف).
3. إجراء الحسابات وتحديد قرار التنبيه.
4. إرسال رسالة تيليجرام عند الحاجة.
5. تحديث الحالة في جداول جوجل وتسجيل الدورة في التاريخ.
6. إدارة تنبيهات الأعطال، القفزات المشبوهة، ونبض الحياة اليومي للمشرف (Health Alerts & Daily Heartbeat).

أمان تام: عدم طباعة أو تسجيل أي أسرار، وعدم طباعة تفاصيل الاستثناءات (str(e))
أو الـ tracebacks في الأخطاء غير المتوقعة لحماية المستودع العام.
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import sys
from typing import Any, Callable
from zoneinfo import ZoneInfo

from gold_radar.alert_logic import AlertState, Decision, decide
from gold_radar.calc import derived_karat_price, fair_price_24k, gap, market_status
from gold_radar.config import (
    ALERT_AFTER_FAILURES,
    HEARTBEAT_HOUR_LOCAL,
    HISTORY_EVERY_RUN,
    MESSAGE_TIMEZONE,
    PRICE_SIDE,
    REALERT_AFTER_HOURS,
)
from gold_radar.message import MessageData, build_message
from gold_radar.sources.gold_api import fetch_ounce_price
from gold_radar.sources.isagha import fetch_local_prices
from gold_radar.sources.models import LocalPrices, OuncePrice, UsdRate
from gold_radar.sources.usd import get_usd_rate
from gold_radar.telegram_client import send_message
from gold_radar.sheets_store import (
    HealthState,
    SheetsHandle,
    append_history,
    ensure_sheets,
    open_store,
    read_health_state,
    read_state,
    write_health_state,
    write_state,
)

# ضبط ترميز المخرجات لدعم العربية
sys.stdout.reconfigure(encoding="utf-8")


@dataclass
class Dependencies:
    """كائن حقن الاعتماديات لتمكين الاختبارات المعزولة بدون شبكة."""
    fetch_ounce: Callable[[], OuncePrice]
    fetch_local_prices: Callable[[], LocalPrices]
    fetch_usd_rate: Callable[[], UsdRate]
    read_state: Callable[[], AlertState]
    write_state: Callable[[AlertState], None]
    append_history: Callable[[dict[str, Any]], None]
    send_message: Callable[[str], None]
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    read_health_state: Callable[[], HealthState] = lambda: HealthState()
    write_health_state: Callable[[HealthState], None] = lambda h: None
    send_admin_message: Callable[[str], None] | None = None


@dataclass
class RunResult:
    """نتيجة تشغيل دورة الفحص."""
    success: bool
    action: str
    message_sent: bool
    state_saved: bool
    error_message: str | None = None
    decision: Decision | None = None
    message_text: str | None = None


def _safe_send_admin(send_admin: Callable[[str], None], text: str) -> None:
    """إرسال تنبيه للمشرف بأمان، وابتلاع أي استثناء مع طباعة سطر آمن."""
    try:
        send_admin(text)
    except Exception as exc:
        print(f"⚠️ تعذر إرسال تنبيه المشرف [{exc.__class__.__name__}].")


def _handle_failure(deps: Dependencies, safe_reason: str, is_sheet_unreadable: bool = False) -> None:
    """معالجة دورة فاشلة: زيادة عداد الأعطال وإرسال التنبيه عند بلوغ الحد أو مرور المهلة."""
    current_time = deps.now()
    admin_sender = deps.send_admin_message if deps.send_admin_message is not None else deps.send_message

    if is_sheet_unreadable:
        # إذا كان الجدول نفسه غير قابل للقراءة، نرسل فقط إذا كانت ساعة UTC تقبل القسمة على 6 والدقيقة أقل من 10
        if current_time.hour % 6 == 0 and current_time.minute < 10:
            msg = f"⚠️ مرصاد الذهب: فشلت الدورة (تعذر الاتصال بجدول جوجل)\nالسبب: {safe_reason}"
            _safe_send_admin(admin_sender, msg)
        return

    try:
        health = deps.read_health_state()
    except Exception:
        # تعذر قراءة الحالة الصحية نعاملها كحالة جدول غير مقروء
        if current_time.hour % 6 == 0 and current_time.minute < 10:
            msg = f"⚠️ مرصاد الذهب: تعذر قراءة الحالة الصحية\nالسبب: {safe_reason}"
            _safe_send_admin(admin_sender, msg)
        return

    health.consecutive_failures += 1

    should_alert = False
    if health.consecutive_failures == ALERT_AFTER_FAILURES:
        should_alert = True
    elif health.consecutive_failures > ALERT_AFTER_FAILURES:
        if health.last_failure_alert_at:
            try:
                last_alert_dt = datetime.fromisoformat(health.last_failure_alert_at)
                elapsed_hours = (current_time - last_alert_dt).total_seconds() / 3600.0
                if elapsed_hours >= REALERT_AFTER_HOURS:
                    should_alert = True
            except Exception:
                should_alert = True
        else:
            should_alert = True

    if should_alert:
        msg = f"⚠️ مرصاد الذهب: فشلت {health.consecutive_failures} دورات متتالية\nالسبب: {safe_reason}"
        _safe_send_admin(admin_sender, msg)
        health.last_failure_alert_at = current_time.isoformat()

    try:
        deps.write_health_state(health)
    except Exception as exc:
        print(f"⚠️ تعذر حفظ الحالة الصحية بعد الفشل [{exc.__class__.__name__}].")


def run_once(deps: Dependencies, dry_run: bool = False) -> RunResult:
    """
    تنفيذ دورة فحص واحدة لمنظومة مرصاد الذهب.
    """
    current_time = deps.now()

    if dry_run:
        print("🟡 تشغيل تجريبي للمعاينة (--dry-run): لن يتم الاتصال بتيليجرام أو جداول جوجل.")

    # 1. قراءة الحالة السابقة
    if dry_run:
        state = AlertState()
        print("  • حالة سابقة افتراضية (دورة أولى).")
    else:
        try:
            state = deps.read_state()
            print("  • قراءة الحالة السابقة من جداول جوجل: نجحت.")
        except Exception as exc:
            err_msg = f"فشل قراءة الحالة من جداول جوجل: {exc.__class__.__name__}"
            print(f"❌ {err_msg}")
            _handle_failure(deps, safe_reason="تعذر قراءة الحالة السابقة من جداول جوجل", is_sheet_unreadable=True)
            return RunResult(success=False, action="error", message_sent=False, state_saved=False, error_message=err_msg)

    # 2. جلب الأسعار اللحظية
    try:
        ounce = deps.fetch_ounce()
        local = deps.fetch_local_prices()
        usd = deps.fetch_usd_rate()
        print(f"  • جلب البيانات: أونصة={ounce.usd:.2f}$ | ع24={local.sell_24k:.2f} ج.م | دولار={usd.rate:.2f} ج.م")
    except Exception as exc:
        err_msg = f"فشل جلب أسعار أحد المصادر: {exc.__class__.__name__}"
        print(f"❌ {err_msg}")
        if not dry_run:
            _handle_failure(deps, safe_reason="تعذر جلب البيانات من مصادر الأسعار", is_sheet_unreadable=False)
        return RunResult(success=False, action="error", message_sent=False, state_saved=False, error_message=err_msg)

    # 3. الحسابات
    sel_24k = local.sell_24k if PRICE_SIDE == "sell" else local.buy_24k
    sel_21k = local.sell_21k if PRICE_SIDE == "sell" else local.buy_21k
    sel_18k = local.sell_18k if PRICE_SIDE == "sell" else local.buy_18k
    sel_pound = local.sell_pound if PRICE_SIDE == "sell" else local.buy_pound

    calc_14k = derived_karat_price(sel_24k, 14)
    fair_24 = fair_price_24k(ounce.usd, usd.rate)
    gap_val, gap_percent = gap(sel_24k, fair_24)
    status_key = market_status(gap_percent)

    # 4. اتخاذ القرار
    decision = decide(sel_24k, state)
    print(f"  • قرار المنظومة: {decision.action} (الاتجاه: {decision.direction or 'لا يوجد'} | التغير: {decision.change_pct if decision.change_pct is not None else 0.0:+.2f}%)")

    # تجهيز كائن نص الرسالة
    msg_data = MessageData(
        price_24k=sel_24k,
        price_21k=sel_21k,
        price_18k=sel_18k,
        price_14k=calc_14k,
        gold_pound=sel_pound,
        ounce_usd=ounce.usd,
        usd_egp=usd.rate,
        fair_24k=fair_24,
        gap_egp=gap_val,
        gap_pct=gap_percent,
        status=status_key,
        updated_at_utc=current_time,
    )
    message_text = build_message(msg_data)

    if dry_run:
        print("\n--- [نص الرسالة للمعاينة] ---")
        print(message_text)
        print("--- [نهاية المعاينة] ---\n")
        return RunResult(
            success=True,
            action=decision.action,
            message_sent=False,
            state_saved=False,
            decision=decision,
            message_text=message_text,
        )

    # 5. معالجة الإجراءات والإرسال
    message_sent = False
    if decision.action in ("first_alert", "alert"):
        try:
            deps.send_message(message_text)
            message_sent = True
            print("  • إرسال تنبيه تيليجرام: تم بنجاح ✅")
        except Exception as exc:
            err_msg = f"فشل إرسال رسالة تيليجرام: {exc.__class__.__name__}"
            print(f"❌ {err_msg}")
            _handle_failure(deps, safe_reason="تعذر إرسال تنبيه تيليجرام للعملاء", is_sheet_unreadable=False)
            return RunResult(
                success=False,
                action=decision.action,
                message_sent=False,
                state_saved=False,
                error_message=err_msg,
                decision=decision,
            )
    elif decision.action == "suspicious":
        print("  ⚠️ تنبيه: قفزة سعرية مشبوهة! تم تجميد التنبيه وسيتم تسجيل الحالة للمتابعة.")
        if decision.new_state.suspicious_count == 1:
            admin_sender = deps.send_admin_message if deps.send_admin_message is not None else deps.send_message
            old_p = state.last_seen_price if state.last_seen_price is not None else (state.last_alert_price or sel_24k)
            change_p = decision.change_pct if decision.change_pct is not None else 0.0
            suspicious_msg = (
                f"⚠️ قفزة مشبوهة في السعر لم تُرسل للعملاء\n"
                f"السعر السابق: {old_p:,.2f} ج.م\n"
                f"السعر الجديد: {sel_24k:,.2f} ج.م\n"
                f"نسبة التغير: {change_p:+.2f}%"
            )
            _safe_send_admin(admin_sender, suspicious_msg)
    else:
        print("  • لا يوجد تغير كافٍ لإرسال تنبيه (الحالة مستقرة).")

    # 6. تحديث الحالة في جداول جوجل وتسجيل التاريخ
    state_saved = False
    try:
        deps.write_state(decision.new_state)
        state_saved = True
        print("  • حفظ الحالة الجديدة في جداول جوجل: تم بنجاح.")

        # تسجيل صف في ورقة التاريخ
        should_record_history = HISTORY_EVERY_RUN or decision.action in ("first_alert", "alert", "suspicious")
        if should_record_history:
            history_row = {
                "time": current_time.isoformat(),
                "ounce_usd": round(ounce.usd, 2),
                "usd_egp": round(usd.rate, 4),
                "usd_source": usd.source_name,
                "buy_24k": round(local.buy_24k, 2),
                "sell_24k": round(local.sell_24k, 2),
                "sell_21k": round(local.sell_21k, 2),
                "sell_18k": round(local.sell_18k, 2),
                "calculated_14k": round(calc_14k, 2),
                "gold_pound_sell": round(local.sell_pound, 2),
                "fair_24k": round(fair_24, 2),
                "gap_egp": round(gap_val, 2),
                "gap_pct": round(gap_percent, 2),
                "status": status_key,
                "action": decision.action,
                "change_pct": round(decision.change_pct, 2) if decision.change_pct is not None else "",
            }
            deps.append_history(history_row)
            print("  • تسجيل بيانات الدورة في ورقة التاريخ: تم بنجاح.")

    except Exception as exc:
        err_msg = f"فشل حفظ الحالة أو التاريخ في جداول جوجل: {exc.__class__.__name__}"
        print(f"❌ {err_msg}")
        _handle_failure(deps, safe_reason="تعذر حفظ الحالة أو التاريخ في جداول جوجل", is_sheet_unreadable=False)
        return RunResult(
            success=False,
            action=decision.action,
            message_sent=message_sent,
            state_saved=state_saved,
            error_message=err_msg,
            decision=decision,
        )

    # 7. عند نجاح الدورة بالكامل: معالجة التعافي ونبض الحياة اليومي
    admin_sender = deps.send_admin_message if deps.send_admin_message is not None else deps.send_message
    try:
        health = deps.read_health_state()
        # إذا كان قد أُرسل تنبيه عطل سابقاً، نرسل إشعار التعافي
        if health.last_failure_alert_at is not None:
            _safe_send_admin(admin_sender, "✅ مرصاد الذهب رجع يشتغل")
            health.last_failure_alert_at = None

        # تصفير عداد الأعطال بعد أي دورة ناجحة
        health.consecutive_failures = 0

        # نبض الحياة اليومي (Daily Heartbeat) بتوقيت القاهرة
        cairo_tz = ZoneInfo(MESSAGE_TIMEZONE)
        cairo_now = current_time.astimezone(cairo_tz)
        today_cairo_str = cairo_now.strftime("%Y-%m-%d")

        if cairo_now.hour >= HEARTBEAT_HOUR_LOCAL and health.last_heartbeat_date != today_cairo_str:
            status_arabic = {
                "higher": "أعلى",
                "lower": "أقل",
                "balanced": "متوازن",
            }.get(status_key, status_key)
            heartbeat_msg = (
                f"💓 مرصاد الذهب شغال\n"
                f"💰 سعر ع24: {sel_24k:,.2f} ج.م\n"
                f"📈 نسبة الفجوة: {gap_percent:+.2f}%\n"
                f"📊 حالة السوق: {status_arabic}"
            )
            _safe_send_admin(admin_sender, heartbeat_msg)
            health.last_heartbeat_date = today_cairo_str

        deps.write_health_state(health)
    except Exception as exc:
        print(f"⚠️ تعذر تحديث الحالة الصحية أو نبض الحياة [{exc.__class__.__name__}].")

    return RunResult(
        success=True,
        action=decision.action,
        message_sent=message_sent,
        state_saved=state_saved,
        decision=decision,
        message_text=message_text,
    )


def main(argv: list[str] | None = None) -> int:
    """
    نقطة الدخول الرئيسية: التحقق من البيئة، بناء الاعتماديات، وتشغيل الدورة.
    تعيد 0 عند النجاح أو 1 عند الفشل.
    """
    parser = argparse.ArgumentParser(description="مرصاد الذهب - نظام مراقبة أسعار الذهب والتنبيهات")
    parser.add_argument("--dry-run", action="store_true", help="تشغيل تجريبي للمعاينة دون إرسال رسائل أو تعديل الجداول")
    args = parser.parse_args(argv)

    print("=" * 65)
    print("🚀 بدء تشغيل دورة مرصاد الذهب (Gold Radar)")
    print("=" * 65)

    if args.dry_run:
        deps = Dependencies(
            fetch_ounce=fetch_ounce_price,
            fetch_local_prices=fetch_local_prices,
            fetch_usd_rate=get_usd_rate,
            read_state=lambda: AlertState(),
            write_state=lambda s: None,
            append_history=lambda r: None,
            send_message=lambda t: None,
            now=lambda: datetime.now(timezone.utc),
            read_health_state=lambda: HealthState(),
            write_health_state=lambda h: None,
            send_admin_message=lambda t: None,
        )
        try:
            res = run_once(deps, dry_run=True)
            return 0 if res.success else 1
        except Exception as exc:
            print(f"❌ خطأ أثناء المعاينة التجريبية [{exc.__class__.__name__}].")
            return 1

    # التشغيل الحقيقي: التحقق من المتغيرات
    required_env_vars = [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "GOOGLE_SHEET_ID",
    ]
    for var_name in required_env_vars:
        if not os.environ.get(var_name):
            print(f"❌ خطأ: متغير البيئة المطلوب غير موجود: {var_name}")
            return 1

    tg_token = os.environ["TELEGRAM_BOT_TOKEN"]
    tg_customer_chat_id = os.environ["TELEGRAM_CHAT_ID"]
    tg_admin_chat_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "").strip() or tg_customer_chat_id
    sa_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    sheet_id = os.environ["GOOGLE_SHEET_ID"]

    send_customer = lambda t: send_message(t, tg_token, tg_customer_chat_id)
    send_admin = lambda t: send_message(t, tg_token, tg_admin_chat_id)

    try:
        handle = open_store(sa_json, sheet_id)
        ensure_sheets(handle)

        deps = Dependencies(
            fetch_ounce=fetch_ounce_price,
            fetch_local_prices=fetch_local_prices,
            fetch_usd_rate=get_usd_rate,
            read_state=lambda: read_state(handle),
            write_state=lambda s: write_state(handle, s),
            append_history=lambda r: append_history(handle, r),
            send_message=send_customer,
            now=lambda: datetime.now(timezone.utc),
            read_health_state=lambda: read_health_state(handle),
            write_health_state=lambda h: write_health_state(handle, h),
            send_admin_message=send_admin,
        )

        result = run_once(deps, dry_run=False)
        print("=" * 65)
        if result.success:
            print("✅ اكتملت الدورة بنجاح.")
            return 0
        else:
            print("❌ انتهت الدورة مع وجود أخطاء.")
            return 1

    except Exception as exc:
        now_utc = datetime.now(timezone.utc)
        if now_utc.hour % 6 == 0 and now_utc.minute < 10:
            _safe_send_admin(send_admin, "⚠️ مرصاد الذهب: تعذر الاتصال بجدول جوجل\nالسبب: تعذر فتح أو تهيئة جداول جوجل")
        print(f"❌ خطأ أثناء تشغيل الدورة [{exc.__class__.__name__}].")
        print("=" * 65)
        return 1


if __name__ == "__main__":
    sys.exit(main())
