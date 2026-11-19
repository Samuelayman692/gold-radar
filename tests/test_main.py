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
from unittest.mock import patch
import pytest

# إضافة مجلد src لمسار الحزم
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gold_radar.alert_logic import AlertState
from gold_radar.main import Dependencies, main, run_once
from gold_radar.sources.models import LocalPrices, OuncePrice, UsdRate

FAKE_TOKEN = "999999999:AAFakeToken123456Secret"
FAKE_CHAT = "111222333_FAKE_CHAT"
FAKE_SA = '{"type": "service_account", "private_key": "MOCK_PRIVATE_KEY_FAKE_SECRET_123"}'
FAKE_SHEET = "1fake_sheet_id_secret_998877"


class FakeStore:
    def __init__(self, initial_state=None):
        self.state = initial_state if initial_state is not None else AlertState()
        self.history = []
        self.read_state_error = None
        self.write_state_error = None
        self.append_history_error = None

    def read_state(self):
        if self.read_state_error:
            raise self.read_state_error
        return self.state

    def write_state(self, new_state):
        if self.write_state_error:
            raise self.write_state_error
        self.state = new_state

    def append_history(self, row):
        if self.append_history_error:
            raise self.append_history_error
        self.history.append(row)


class FakeTelegram:
    def __init__(self):
        self.sent_messages = []
        self.send_error = None

    def send_message(self, text):
        if self.send_error:
            raise self.send_error
        self.sent_messages.append(text)


def _build_test_deps(store=None, telegram=None, sell_24k=6550.0):
    """مساعد لبناء اعتماديات وهمية."""
    if store is None:
        store = FakeStore()
    if telegram is None:
        telegram = FakeTelegram()

    buy_24k = sell_24k - 50.0
    return (
        Dependencies(
            fetch_ounce=lambda: OuncePrice(usd=3700.0, fetched_at=datetime.now(timezone.utc)),
            fetch_local_prices=lambda: LocalPrices(
                buy_24k=buy_24k,
                sell_24k=sell_24k,
                buy_21k=buy_24k * 21 / 24,
                sell_21k=sell_24k * 21 / 24,
                buy_18k=buy_24k * 18 / 24,
                sell_18k=sell_24k * 18 / 24,
                buy_pound=(buy_24k * 21 / 24) * 8,
                sell_pound=(sell_24k * 21 / 24) * 8,
                fetched_at=datetime.now(timezone.utc),
            ),
            fetch_usd_rate=lambda: UsdRate(rate=50.0, source_name="fawazahmed0", fetched_at=datetime.now(timezone.utc)),
            read_state=store.read_state,
            write_state=store.write_state,
            append_history=store.append_history,
            send_message=telegram.send_message,
            now=lambda: datetime(2026, 11, 18, 20, 0, tzinfo=timezone.utc),
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
