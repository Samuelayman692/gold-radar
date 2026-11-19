"""
المنسق الرئيسي لمنظومة مرصاد الذهب (src/gold_radar/main.py).
لمشروع مرصاد الذهب (Gold Radar).

يقوم بالتنسيق الكامل للدورة:
1. قراءة الحالة السابقة من جداول جوجل.
2. جلب الأسعار الحية (الأونصة، السوق المحلي، سعر الصرف).
3. إجراء الحسابات وتحديد قرار التنبيه.
4. إرسال رسالة تيليجرام عند الحاجة.
5. تحديث الحالة في جداول جوجل وتسجيل الدورة في التاريخ.

أمان تام: عدم طباعة أو تسجيل أي أسرار، وعدم طباعة تفاصيل الاستثناءات (str(e))
أو الـ tracebacks في الأخطاء غير المتوقعة لحماية المستودع العام.
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import sys
from typing import Any, Callable

from gold_radar.alert_logic import AlertState, Decision, decide
from gold_radar.calc import derived_karat_price, fair_price_24k, gap, market_status
from gold_radar.config import HISTORY_EVERY_RUN, PRICE_SIDE
from gold_radar.message import MessageData, build_message
from gold_radar.sources.gold_api import fetch_ounce_price
from gold_radar.sources.isagha import fetch_local_prices
from gold_radar.sources.models import LocalPrices, OuncePrice, UsdRate
from gold_radar.sources.usd import get_usd_rate
from gold_radar.telegram_client import send_message
from gold_radar.sheets_store import (
    SheetsHandle,
    append_history,
    ensure_sheets,
    open_store,
    read_state,
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
            err_msg = f"فشل قراءة الحالة من جداول جوجل: {exc}"
            print(f"❌ {err_msg}")
            return RunResult(success=False, action="error", message_sent=False, state_saved=False, error_message=err_msg)

    # 2. جلب الأسعار اللحظية
    try:
        ounce = deps.fetch_ounce()
        local = deps.fetch_local_prices()
        usd = deps.fetch_usd_rate()
        print(f"  • جلب البيانات: أونصة={ounce.usd:.2f}$ | ع24={local.sell_24k:.2f} ج.م | دولار={usd.rate:.2f} ج.م")
    except Exception as exc:
        err_msg = f"فشل جلب أسعار أحد المصادر: {exc}"
        print(f"❌ {err_msg}")
        return RunResult(success=False, action="error", message_sent=False, state_saved=False, error_message=err_msg)

    # 3. الحسابات
    # تحديد السعر المعتمد بناءً على PRICE_SIDE في الإعدادات ("sell" أو "buy")
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
            err_msg = f"فشل إرسال رسالة تيليجرام: {exc}"
            print(f"❌ {err_msg}")
            # لا نحدث الحالة لضمان إعادة المحاولة في الدورة القادمة
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
        err_msg = f"فشل حفظ الحالة أو التاريخ في جداول جوجل: {exc}"
        print(f"❌ {err_msg}")
        if message_sent:
            print("⚠️ تحذير مهم: تم إرسال الرسالة إلى تيليجرام ولكن تعذر حفظ الحالة في جوجل شيت؛ قد تتكرر الرسالة في الدورة القادمة.")
        return RunResult(
            success=False,
            action=decision.action,
            message_sent=message_sent,
            state_saved=state_saved,
            error_message=err_msg,
            decision=decision,
        )

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
        # في وضع المعاينة لا نحتاج لمفاتيح تيليجرام أو جوجل
        deps = Dependencies(
            fetch_ounce=fetch_ounce_price,
            fetch_local_prices=fetch_local_prices,
            fetch_usd_rate=get_usd_rate,
            read_state=lambda: AlertState(),
            write_state=lambda s: None,
            append_history=lambda r: None,
            send_message=lambda t: None,
            now=lambda: datetime.now(timezone.utc),
        )
        try:
            res = run_once(deps, dry_run=True)
            return 0 if res.success else 1
        except Exception as exc:
            # حماية كاملة للسجلات
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
    tg_chat_id = os.environ["TELEGRAM_CHAT_ID"]
    sa_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    sheet_id = os.environ["GOOGLE_SHEET_ID"]

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
            send_message=lambda t: send_message(t, tg_token, tg_chat_id),
            now=lambda: datetime.now(timezone.utc),
        )

        result = run_once(deps, dry_run=False)
        print("=" * 65)
        if result.success:
            print("✅ اكتملت الدورة بنجاح.")
            return 0
        else:
            print("❌ انتهت الدورة مع وجود أخطاء.")
            return 1

    except (RuntimeError, ValueError) as exc:
        print(f"❌ خطأ أثناء تشغيل الدورة: {exc}")
        print("=" * 65)
        return 1
    except Exception as exc:
        # للأخطاء غير المتوقعة: طباعة اسم فئة الخطأ فقط بدون tracebacks
        print(f"❌ خطأ غير متوقع [{exc.__class__.__name__}]: تعذر إكمال الدورة بنجاح.")
        print("=" * 65)
        return 1


if __name__ == "__main__":
    sys.exit(main())
