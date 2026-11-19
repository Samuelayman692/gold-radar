"""
اختبارات وحدة المنسق الرئيسي (tests/test_main.py)
لمشروع مرصاد الذهب (Gold Radar).

اختبارات نقية بالكامل بدون أي اتصالات شبكية وتستخدم اعتمادات ومصادر وهمية (Fakes):
1. الدورة الأولى ترسل رسالة وتكتب الحالة والتاريخ.
2. الدورة الثانية بنفس السعر لا ترسل شيئاً ولكن تحفظ الحالة والتاريخ.
3. تغير 0.25% أو أكثر يرسل تنبيهاً ويحدث سعر الأساس.
4. فشل تيليجرام يترك الحالة دون تغيير ويعيد كود 1.
5. فشل أحد المصادر لا يرسل ولا يكتب شيئاً ويعيد كود 1.
6. تلف ورقة الحالة لا يرسل شيئاً ويعيد كود 1.
7. القفزة المشبوهة لا ترسل شيئاً وتحفظ الحالة والتاريخ وتعيد 0.
8. المعاينة التجريبية (--dry-run) لا تلمس تيليجرام أو جداول جوجل.
9. النص المرسل يعتمد أسعار جانب البيع (sell) مع تمييز عيار 14 فقط بـ (محسوب).
10. التحقق الصارم في كل حالة فشل من خلو المخرجات المطبوعة من أي أسرار.
"""

from datetime import datetime, timezone
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# إضافة مجلد src لمسار الحزم
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gold_radar.alert_logic import AlertState
from gold_radar.main import Dependencies, RunResult, main, run_once
from gold_radar.sheets_store import HealthState
from gold_radar.sources.models import LocalPrices, OuncePrice, UsdRate

FAKE_TOKEN = "999999999:AAFakeToken123456Secret"
FAKE_CHAT = "111222333_FAKE_CHAT"
FAKE_ADMIN_CHAT = "444555666_FAKE_ADMIN_CHAT"
FAKE_SA = '{"type": "service_account", "private_key": "MOCK_PRIVATE_KEY_FAKE_SECRET_123"}'
FAKE_SHEET = "1fake_sheet_id_secret_998877"


class FakeStore:
    def __init__(self, initial_state=None, initial_health=None):
        self.state = initial_state if initial_state is not None else AlertState()
        self.health = initial_health if initial_health is not None else HealthState()
        self.history = []
        self.read_state_error = None
        self.write_state_error = None
        self.append_history_error = None
        self.read_health_error = None
        self.write_health_error = None

    def read_state(self):
        if self.read_state_error:
            raise self.read_state_error
        return self.state

    def write_state(self, new_state):
        if self.write_state_error:
            raise self.write_state_error
        self.state = new_state

    def read_health_state(self):
        if self.read_health_error:
            raise self.read_health_error
        return self.health

    def write_health_state(self, new_health):
        if self.write_health_error:
            raise self.write_health_error
        self.health = new_health

    def append_history(self, row):
        if self.append_history_error:
            raise self.append_history_error
        self.history.append(row)


class FakeTelegram:
    def __init__(self):
        self.sent_messages = []
        self.admin_messages = []
        self.send_error = None
        self.send_admin_error = None

    def send_message(self, text):
        if self.send_error:
            raise self.send_error
        self.sent_messages.append(text)

    def send_admin_message(self, text):
        if self.send_admin_error:
            raise self.send_admin_error
        self.admin_messages.append(text)


def _build_test_deps(store=None, telegram=None, sell_24k=6550.0, now_dt=None):
    """مساعد لبناء اعتماديات وهمية."""
    if store is None:
        store = FakeStore()
    if telegram is None:
        telegram = FakeTelegram()
    if now_dt is None:
        now_dt = datetime(2026, 11, 18, 20, 0, tzinfo=timezone.utc)

    buy_24k = sell_24k - 50.0
    return (
        Dependencies(
            fetch_ounce=lambda: OuncePrice(usd=3700.0, fetched_at=now_dt),
            fetch_local_prices=lambda: LocalPrices(
                buy_24k=buy_24k,
                sell_24k=sell_24k,
                buy_21k=buy_24k * 21 / 24,
                sell_21k=sell_24k * 21 / 24,
                buy_18k=buy_24k * 18 / 24,
                sell_18k=sell_24k * 18 / 24,
                buy_pound=(buy_24k * 21 / 24) * 8,
                sell_pound=(sell_24k * 21 / 24) * 8,
                fetched_at=now_dt,
            ),
            fetch_usd_rate=lambda: UsdRate(rate=50.0, source_name="fawazahmed0", fetched_at=now_dt),
            read_state=store.read_state,
            write_state=store.write_state,
            append_history=store.append_history,
            send_message=telegram.send_message,
            now=lambda: now_dt,
            read_health_state=store.read_health_state,
            write_health_state=store.write_health_state,
            send_admin_message=telegram.send_admin_message,
        ),
        store,
        telegram,
    )


def test_first_run_sends_and_writes_state_and_history():
    """الدورة الأولى ترسل رسالة وتكتب الحالة والتاريخ."""
    deps, store, tg = _build_test_deps(sell_24k=6550.0)
    res = run_once(deps, dry_run=False)

    assert res.success is True
    assert res.action == "first_alert"
    assert res.message_sent is True
    assert res.state_saved is True
    assert len(tg.sent_messages) == 1
    assert store.state.last_alert_price == 6550.0
    assert len(store.history) == 1


def test_second_run_same_price_sends_nothing_writes_state():
    """الدورة الثانية بنفس السعر لا ترسل شيئاً ولكن تحدث الحالة وتكتب التاريخ."""
    initial = AlertState(last_alert_price=6550.0, last_seen_price=6550.0)
    store = FakeStore(initial_state=initial)
    deps, store, tg = _build_test_deps(store=store, sell_24k=6550.0)

    res = run_once(deps, dry_run=False)

    assert res.success is True
    assert res.action == "none"
    assert res.message_sent is False
    assert len(tg.sent_messages) == 0
    assert store.state.last_alert_price == 6550.0
    assert len(store.history) == 1


def test_move_025_percent_sends_and_updates_alert_price():
    """تغير بنسبة 0.25% أو أكثر يرسل تنبيهاً ويحدث سعر الأساس."""
    initial = AlertState(last_alert_price=6550.0, last_seen_price=6550.0)
    store = FakeStore(initial_state=initial)
    # تغير من 6550 إلى 6570 (زيادة 0.305% > 0.25%)
    deps, store, tg = _build_test_deps(store=store, sell_24k=6570.0)

    res = run_once(deps, dry_run=False)

    assert res.success is True
    assert res.action == "alert"
    assert res.message_sent is True
    assert len(tg.sent_messages) == 1
    assert store.state.last_alert_price == 6570.0


def test_telegram_failure_leaves_state_unchanged_and_fails():
    """فشل تيليجرام يترك الحالة دون تعديل ويعيد success=False."""
    store = FakeStore()
    tg = FakeTelegram()
    tg.send_error = RuntimeError("انقطاع الاتصال بتيليجرام")
    deps, store, tg = _build_test_deps(store=store, telegram=tg, sell_24k=6550.0)

    res = run_once(deps, dry_run=False)

    assert res.success is False
    assert res.message_sent is False
    assert res.state_saved is False
    # الحالة تبقى كما هي (None) ليتم إعادة المحاولة في الدورة التالية
    assert store.state.last_alert_price is None


def test_failing_source_sends_and_writes_nothing():
    """فشل أحد المصادر يوقف الدورة دون إرسال رسائل أو تغيير الحالة."""
    initial = AlertState(last_alert_price=6550.0, last_seen_price=6550.0)
    store = FakeStore(initial_state=initial)
    deps, store, tg = _build_test_deps(store=store)

    # محاكاة عطل في مصدر الذهب
    deps.fetch_ounce = lambda: (_ for _ in ()).throw(RuntimeError("تعطل Gold-API"))

    res = run_once(deps, dry_run=False)

    assert res.success is False
    assert len(tg.sent_messages) == 0
    assert len(store.history) == 0
    assert store.state.last_alert_price == 6550.0


def test_unreadable_state_sends_nothing_and_fails():
    """تلف ورقة الحالة يوقف الدورة فوراً دون إرسال أي رسائل."""
    store = FakeStore()
    store.read_state_error = RuntimeError("ورقة الحالة تالفة")
    deps, store, tg = _build_test_deps(store=store)

    res = run_once(deps, dry_run=False)

    assert res.success is False
    assert len(tg.sent_messages) == 0


def test_suspicious_jump_sends_nothing_writes_state_history_returns_success():
    """القفزة السعرية المشبوهة (6%) لا ترسل تنبيهاً، وتسجل في الحالة والتاريخ، وتعتبر دورة ناجحة."""
    initial = AlertState(last_alert_price=6550.0, last_seen_price=6550.0)
    store = FakeStore(initial_state=initial)
    # 6550 * 1.06 = 6943.0 (قفزة 6%)
    deps, store, tg = _build_test_deps(store=store, sell_24k=6943.0)

    res = run_once(deps, dry_run=False)

    assert res.success is True
    assert res.action == "suspicious"
    assert res.message_sent is False
    assert len(tg.sent_messages) == 0
    assert store.state.suspicious_count == 1
    assert store.state.last_suspicious_price == 6943.0
    assert store.state.last_alert_price == 6550.0  # لم يتغير
    assert len(store.history) == 1


def test_dry_run_touches_neither_telegram_nor_sheets():
    """المعاينة التجريبية لا تستدعي تيليجرام ولا جداول جوجل إطلاقاً."""
    store = FakeStore()
    tg = FakeTelegram()
    # إذا تم استدعاء store أو tg ترفع خطأ فوراً للتأكد من عدم لمسهما
    store.read_state = lambda: (_ for _ in ()).throw(AssertionError("تم استدعاء read_state في dry-run!"))
    store.write_state = lambda s: (_ for _ in ()).throw(AssertionError("تم استدعاء write_state في dry-run!"))
    tg.send_message = lambda t: (_ for _ in ()).throw(AssertionError("تم استدعاء send_message في dry-run!"))

    deps, _, _ = _build_test_deps(store=store, telegram=tg)

    res = run_once(deps, dry_run=True)

    assert res.success is True
    assert res.message_sent is False
    assert res.state_saved is False
    assert res.message_text is not None


def test_sent_text_uses_sell_side_numbers_and_14k_tagged():
    """التحقق من أن الرسالة تعتمد أرقام جانب البيع، وأن عيار 14 فقط موسوم بـ (محسوب)."""
    deps, store, tg = _build_test_deps(sell_24k=6550.0)
    res = run_once(deps, dry_run=False)

    msg = tg.sent_messages[0]
    # التأكد من استخدام سعر البيع 6550 وليس الشراء 6500
    assert "💰 السعر المحلي ع24 : 6,550.00 ج.م" in msg
    assert "💰 السعر المحلي ع14" in msg
    assert " (محسوب)" in msg
    assert msg.count("محسوب") == 1


def test_failure_output_contains_no_secrets(capsys, monkeypatch):
    """في أي حالة فشل لـ main()، التأكد التام من خلو المخرجات المطبوعة من الأسرار."""
    # تعيين بيئة تحتوي على أسرار وهمية
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", FAKE_CHAT)
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", FAKE_SA)
    monkeypatch.setenv("GOOGLE_SHEET_ID", FAKE_SHEET)

    # محاكاة عطل غير متوقع في open_store يحتوي على كل الأسرار
    with patch("gold_radar.main.open_store") as mock_open:
        mock_open.side_effect = Exception(
            f"Fatal error with {FAKE_TOKEN} and {FAKE_CHAT} on sheet {FAKE_SHEET} with key {FAKE_SA}"
        )

        exit_code = main([])
        assert exit_code == 1

        captured = capsys.readouterr()
        out_text = captured.out + captured.err

        # التحقق من أن أياً من الأسرار الوهمية لم يظهر إطلاقاً في المخرجات
        assert FAKE_TOKEN not in out_text
        assert FAKE_CHAT not in out_text
        assert FAKE_SHEET not in out_text
        assert "FAKE_SECRET_KEY" not in out_text


def test_third_consecutive_failure_sends_alert_and_fourth_does_not():
    """الفشل الثالث يرسل تنبيهاً واحداً للمشرف، والفشل الرابع لا يرسل تنبيهاً جديداً."""
    store = FakeStore(initial_health=HealthState(consecutive_failures=2))
    deps, store, tg = _build_test_deps(store=store)
    deps.fetch_ounce = lambda: (_ for _ in ()).throw(RuntimeError("Gold API down"))

    # الفشل رقم 3
    res3 = run_once(deps, dry_run=False)
    assert res3.success is False
    assert store.health.consecutive_failures == 3
    assert len(tg.sent_messages) == 0
    assert len(tg.admin_messages) == 1
    assert "فشلت 3 دورات متتالية" in tg.admin_messages[0]

    # الفشل رقم 4
    res4 = run_once(deps, dry_run=False)
    assert res4.success is False
    assert store.health.consecutive_failures == 4
    assert len(tg.sent_messages) == 0
    assert len(tg.admin_messages) == 1  # لم يُرسل تنبيه جديد


def test_realert_after_hours_sends_again():
    """إعادة التنبيه بعد مرور REALERT_AFTER_HOURS (6 ساعات) إذا استمر الفشل."""
    from datetime import timedelta
    now_t = datetime(2026, 11, 18, 20, 0, tzinfo=timezone.utc)
    seven_hours_ago = (now_t - timedelta(hours=7)).isoformat()

    store = FakeStore(initial_health=HealthState(consecutive_failures=10, last_failure_alert_at=seven_hours_ago))
    deps, store, tg = _build_test_deps(store=store, now_dt=now_t)
    deps.fetch_ounce = lambda: (_ for _ in ()).throw(RuntimeError("API down"))

    res = run_once(deps, dry_run=False)
    assert res.success is False
    assert store.health.consecutive_failures == 11
    assert len(tg.admin_messages) == 1
    assert "فشلت 11 دورات متتالية" in tg.admin_messages[0]


def test_recovery_message_after_alert_and_silent_reset_without_one():
    """إرسال رسالة تعافي بعد تنبيه سابق، وإعادة تصفير العداد بصمت إذا لم يُرسل تنبيه."""
    # أ. مع تنبيه سابق: ترسل رسالة تعافي وتصفر العداد
    store_a = FakeStore(initial_health=HealthState(consecutive_failures=3, last_failure_alert_at="2026-11-18T12:00:00+00:00"))
    deps_a, store_a, tg_a = _build_test_deps(store=store_a, sell_24k=6550.0)
    res_a = run_once(deps_a, dry_run=False)
    assert res_a.success is True
    assert "✅ مرصاد الذهب رجع يشتغل" in tg_a.admin_messages
    assert store_a.health.consecutive_failures == 0
    assert store_a.health.last_failure_alert_at is None

    # ب. بدون تنبيه سابق (فشلان فقط): تصفير بصمت دون رسالة تعافي
    store_b = FakeStore(initial_health=HealthState(consecutive_failures=2, last_failure_alert_at=None))
    deps_b, store_b, tg_b = _build_test_deps(store=store_b, sell_24k=6550.0)
    res_b = run_once(deps_b, dry_run=False)
    assert res_b.success is True
    assert "✅ مرصاد الذهب رجع يشتغل" not in tg_b.admin_messages
    assert store_b.health.consecutive_failures == 0


def test_sheet_unreadable_respects_hour_and_minute_rule():
    """عدم إزعاج المشرف إذا كان الجدول تالفاً: إرسال تنبيه فقط إذا كانت الساعة تقبل القسمة على 6 والدقيقة أقل من 10."""
    # حالة 1: ساعة 6:05 (تقبل القسمة على 6 ودقيقة < 10) -> ترسل
    dt_send = datetime(2026, 11, 18, 6, 5, tzinfo=timezone.utc)
    store1 = FakeStore()
    store1.read_state_error = RuntimeError("Corrupt state")
    deps1, store1, tg1 = _build_test_deps(store=store1, now_dt=dt_send)
    res1 = run_once(deps1, dry_run=False)
    assert res1.success is False
    assert len(tg1.admin_messages) == 1
    assert "تعذر الاتصال بجدول جوجل" in tg1.admin_messages[0]

    # حالة 2: ساعة 7:05 (الساعة 7 لا تقبل القسمة على 6) -> لا ترسل
    dt_no_send_hour = datetime(2026, 11, 18, 7, 5, tzinfo=timezone.utc)
    store2 = FakeStore()
    store2.read_state_error = RuntimeError("Corrupt state")
    deps2, store2, tg2 = _build_test_deps(store=store2, now_dt=dt_no_send_hour)
    res2 = run_once(deps2, dry_run=False)
    assert res2.success is False
    assert len(tg2.admin_messages) == 0

    # حالة 3: ساعة 6:15 (الدقيقة 15 ليست أقل من 10) -> لا ترسل
    dt_no_send_min = datetime(2026, 11, 18, 6, 15, tzinfo=timezone.utc)
    store3 = FakeStore()
    store3.read_state_error = RuntimeError("Corrupt state")
    deps3, store3, tg3 = _build_test_deps(store=store3, now_dt=dt_no_send_min)
    res3 = run_once(deps3, dry_run=False)
    assert res3.success is False
    assert len(tg3.admin_messages) == 0


def test_failing_alert_send_does_not_change_exit_code(capsys):
    """فشل إرسال تنبيه المشرف يتم ابتلاعه بأمان ولا يغير كود الخروج."""
    store = FakeStore(initial_health=HealthState(consecutive_failures=2))
    tg = FakeTelegram()
    tg.send_admin_error = RuntimeError("Telegram network timeout")
    deps, store, tg = _build_test_deps(store=store, telegram=tg)
    deps.fetch_ounce = lambda: (_ for _ in ()).throw(RuntimeError("API failure"))

    res = run_once(deps, dry_run=False)
    assert res.success is False
    captured = capsys.readouterr()
    assert "تعذر إرسال تنبيه المشرف" in captured.out


def test_suspicious_sends_once_to_owner_chat():
    """القفزة المشبوهة ترسل تنبيهاً للمشرف مرة واحدة في أول رصد فقط ولا تذهب للعملاء."""
    initial = AlertState(last_alert_price=6550.0, last_seen_price=6550.0)
    store = FakeStore(initial_state=initial, initial_health=HealthState(last_heartbeat_date="2026-11-18"))
    # قفزة 6% مشبوهة
    deps, store, tg = _build_test_deps(store=store, sell_24k=6943.0, now_dt=datetime(2026, 11, 18, 20, 0, tzinfo=timezone.utc))

    # الرصد الأول (suspicious_count == 1)
    res1 = run_once(deps, dry_run=False)
    assert res1.success is True
    assert res1.action == "suspicious"
    assert len(tg.sent_messages) == 0  # العملاء لم يستلموا شيئاً
    assert len(tg.admin_messages) == 1
    assert "قفزة مشبوهة في السعر لم تُرسل للعملاء" in tg.admin_messages[0]

    # الرصد الثاني المستمر (تأكيد السعر وإرسال تنبيه للعملاء، دون تكرار تنبيه المشرف)
    res2 = run_once(deps, dry_run=False)
    assert res2.success is True
    assert res2.action == "alert"
    assert len(tg.sent_messages) == 1  # الآن تأكد السعر وأُرسل للعملاء
    assert len(tg.admin_messages) == 1  # لم يُرسل تنبيه مشبوه إضافي لنفس السلسلة


def test_heartbeat_sends_once_per_cairo_day_and_skipped_in_dry_run():
    """نبض الحياة يرسل مرة واحدة يومياً بتوقيت القاهرة عند أو بعد الساعة 9 صباحاً، ويتخطى في dry-run."""
    # الساعة 8:00 صباحاً بتوقيت القاهرة (UTC+2 تعني 6:00 UTC) -> لا ترسل
    dt_before_9 = datetime(2026, 11, 19, 6, 0, tzinfo=timezone.utc)
    deps1, store1, tg1 = _build_test_deps(now_dt=dt_before_9)
    res1 = run_once(deps1, dry_run=False)
    assert res1.success is True
    assert not any("💓 مرصاد الذهب شغال" in m for m in tg1.admin_messages)

    # الساعة 9:30 صباحاً بتوقيت القاهرة (UTC+2 تعني 7:30 UTC) -> ترسل
    dt_at_9 = datetime(2026, 11, 19, 7, 30, tzinfo=timezone.utc)
    deps2, store2, tg2 = _build_test_deps(now_dt=dt_at_9)
    res2 = run_once(deps2, dry_run=False)
    assert res2.success is True
    assert any("💓 مرصاد الذهب شغال" in m for m in tg2.admin_messages)
    assert store2.health.last_heartbeat_date == "2026-11-19"

    # دورة تالية في نفس اليوم الساعة 10:00 بتوقيت القاهرة -> لا ترسل مرة أخرى
    dt_later_same_day = datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc)
    deps3, store3, tg3 = _build_test_deps(store=store2, now_dt=dt_later_same_day)
    res3 = run_once(deps3, dry_run=False)
    assert res3.success is True
    assert len([m for m in tg3.admin_messages if "💓 مرصاد الذهب شغال" in m]) == 0

    # في وضع المعاينة dry-run -> لا ترسل حتى لو كانت الساعة 9:30
    deps_dry, store_dry, tg_dry = _build_test_deps(now_dt=dt_at_9)
    res_dry = run_once(deps_dry, dry_run=True)
    assert res_dry.success is True
    assert len(tg_dry.admin_messages) == 0


def test_owner_chat_fallback_and_isolation(monkeypatch):
    """عند غياب TELEGRAM_ADMIN_CHAT_ID يتم استخدام TELEGRAM_CHAT_ID، وعند وجوده تُعزل رسائل المشرف تماماً."""
    sent_to = []

    def mock_send(text, token, chat_id):
        sent_to.append((chat_id, text))

    monkeypatch.setattr("gold_radar.main.send_message", mock_send)
    monkeypatch.setattr("gold_radar.main.open_store", lambda s, i: MagicMock())
    monkeypatch.setattr("gold_radar.main.ensure_sheets", lambda h: None)

    # 1. بدون ADMIN_CHAT_ID -> ترسل إلى CHAT_ID
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", FAKE_CHAT)
    monkeypatch.delenv("TELEGRAM_ADMIN_CHAT_ID", raising=False)
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", FAKE_SA)
    monkeypatch.setenv("GOOGLE_SHEET_ID", FAKE_SHEET)

    with patch("gold_radar.main.run_once") as mock_run:
        def do_run(deps, dry_run):
            deps.send_admin_message("رسالة مشرف")
            deps.send_message("رسالة عميل")
            return RunResult(success=True, action="none", message_sent=False, state_saved=True)
        mock_run.side_effect = do_run
        main([])

    assert (FAKE_CHAT, "رسالة مشرف") in sent_to
    assert (FAKE_CHAT, "رسالة عميل") in sent_to

    # 2. بوجود ADMIN_CHAT_ID -> رسائل المشرف تذهب له ورسائل العملاء تذهب لقناة العملاء
    sent_to.clear()
    monkeypatch.setenv("TELEGRAM_ADMIN_CHAT_ID", FAKE_ADMIN_CHAT)
    with patch("gold_radar.main.run_once") as mock_run:
        def do_run(deps, dry_run):
            deps.send_admin_message("رسالة مشرف خاصة")
            deps.send_message("رسالة عميل عامة")
            return RunResult(success=True, action="none", message_sent=False, state_saved=True)
        mock_run.side_effect = do_run
        main([])

    assert (FAKE_ADMIN_CHAT, "رسالة مشرف خاصة") in sent_to
    assert (FAKE_CHAT, "رسالة عميل عامة") in sent_to
    assert (FAKE_CHAT, "رسالة مشرف خاصة") not in sent_to


def test_failure_messages_contain_no_secrets():
    """التحقق في كافة حالات الفشل من خلو الرسائل الموجهة للمشرف من أي أسرار."""
    store = FakeStore(initial_health=HealthState(consecutive_failures=2))
    deps, store, tg = _build_test_deps(store=store)
    deps.fetch_ounce = lambda: (_ for _ in ()).throw(RuntimeError(f"Network error with secret {FAKE_TOKEN}"))

    res = run_once(deps, dry_run=False)
    assert res.success is False
    assert len(tg.admin_messages) == 1
    msg = tg.admin_messages[0]
    assert FAKE_TOKEN not in msg
    assert FAKE_CHAT not in msg
    assert FAKE_SHEET not in msg

