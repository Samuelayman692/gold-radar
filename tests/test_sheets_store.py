"""
اختبارات وحدة تخزين جداول جوجل (tests/test_sheets_store.py)
لمشروع مرصاد الذهب (Gold Radar).

اختبارات نقية بالكامل باستخدام المحاكاة (Mocking) وبدون أي اتصالات شبكية حقيقية:
- قراءة الحالة الفارغة تعطي جميع القيم None
- كتابة الحالة ثم قراءتها ومطابقتها (Round Trip)
- رفض الحالة التالفة أو غير القابلة للقراءة ورفع خطأ صريح
- تطابق ترتيب صف التاريخ بدقة مع ترتيب الأعمدة والترويسات
- فحص أمان صارم في كل استثناء للتأكد من عدم تسريب JSON أو المفتاح الخاص أو معرف الجدول
"""

from unittest.mock import MagicMock, patch
import json
import sys
from pathlib import Path
import pytest

# إضافة مجلد src لمسار الحزم
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gold_radar.alert_logic import AlertState
from gold_radar.sheets_store import (
    HISTORY_COLUMNS,
    STATE_HEADERS,
    SheetsHandle,
    append_history,
    ensure_sheets,
    open_store,
    read_state,
    write_state,
)

FAKE_SHEET_ID = "1a2b3c4d5e6f7g8h9i0_FAKE_SHEET_ID_SECRET"
FAKE_PRIVATE_KEY = "MOCK_TEST_RSA_PRIVATE_KEY_NEVER_REAL_12345"
FAKE_CLIENT_EMAIL = "fake-sa@fake-project.iam.gserviceaccount.com"
FAKE_SA_JSON = json.dumps({
    "type": "service_account",
    "project_id": "fake-project",
    "private_key_id": "fake-key-id",
    "private_key": FAKE_PRIVATE_KEY,
    "client_email": FAKE_CLIENT_EMAIL,
    "client_id": "123456789",
})


def _create_mock_handle():
    """مساعد لإنشاء كائن SheetsHandle وهمي."""
    client = MagicMock()
    spreadsheet = MagicMock()
    return SheetsHandle(client=client, spreadsheet=spreadsheet, sheet_id=FAKE_SHEET_ID)


def test_read_empty_state_gives_none():
    """قراءة ورقة حالة فارغة أو تحتوي الترويسة فقط تعطي None لكافة الأسعار."""
    handle = _create_mock_handle()
    ws_mock = MagicMock()
    handle.spreadsheet.worksheet.return_value = ws_mock

    # 1. فارغة تماماً
    ws_mock.get_all_values.return_value = []
    state1 = read_state(handle)
    assert state1.last_alert_price is None
    assert state1.last_seen_price is None
    assert state1.suspicious_count == 0
    assert state1.last_suspicious_price is None

    # 2. تحتوي فقط على صف الترويسة
    ws_mock.get_all_values.return_value = [STATE_HEADERS]
    state2 = read_state(handle)
    assert state2.last_alert_price is None
    assert state2.last_seen_price is None
    assert state2.suspicious_count == 0

    # 3. تحتوي على المفاتيح ولكن بخلايا فارغة
    ws_mock.get_all_values.return_value = [
        STATE_HEADERS,
        ["last_alert_price", ""],
        ["last_seen_price", ""],
        ["suspicious_count", "0"],
        ["last_suspicious_price", ""],
        ["updated_at", ""],
    ]
    state3 = read_state(handle)
    assert state3.last_alert_price is None
    assert state3.last_seen_price is None
    assert state3.suspicious_count == 0
    assert state3.last_suspicious_price is None


def test_write_and_read_state_round_trip():
    """التحقق من صحة كتابة الحالة ثم قراءتها واسترجاع نفس القيم بدقة."""
    handle = _create_mock_handle()
    ws_mock = MagicMock()
    handle.spreadsheet.worksheet.return_value = ws_mock

    original_state = AlertState(
        last_alert_price=6611.50,
        last_seen_price=6615.00,
        suspicious_count=2,
        last_suspicious_price=6700.00,
    )

    # محاكاة حفظ وتحديث البيانات
    saved_rows = []

    def mock_update(rows, range_name=None):
        nonlocal saved_rows
        saved_rows = rows
        return {"updatedRows": len(rows)}

    ws_mock.update.side_effect = mock_update
    ws_mock.get_all_values.side_effect = lambda: saved_rows

    write_state(handle, original_state)
    assert ws_mock.update.call_count == 1

    read_back_state = read_state(handle)
    assert read_back_state.last_alert_price == original_state.last_alert_price
    assert read_back_state.last_seen_price == original_state.last_seen_price
    assert read_back_state.suspicious_count == original_state.suspicious_count
    assert read_back_state.last_suspicious_price == original_state.last_suspicious_price


def test_unreadable_or_corrupt_state_raises_error():
    """البيانات التالفة أو المفاتيح المفقودة يجب أن ترفع خطأ صريحاً ولا تعود صامتة."""
    handle = _create_mock_handle()
    ws_mock = MagicMock()
    handle.spreadsheet.worksheet.return_value = ws_mock

    # 1. مفاتيح مفقودة
    ws_mock.get_all_values.return_value = [
        STATE_HEADERS,
        ["unknown_key", "123"],
    ]
    with pytest.raises(RuntimeError, match="تالفة أو ينقصها مفاتيح"):
        read_state(handle)

    # 2. أرقام غير صالحة (نص بدلاً من رقم)
    ws_mock.get_all_values.return_value = [
        STATE_HEADERS,
        ["last_alert_price", "INVALID_FLOAT"],
        ["last_seen_price", "6000"],
        ["suspicious_count", "0"],
        ["last_suspicious_price", ""],
    ]
    with pytest.raises(RuntimeError, match="قيمة غير صالحة للحقل"):
        read_state(handle)


def test_history_row_order_matches_headers():
    """التحقق من تطابق ترتيب قيم الصف المضاف مع ترتيب أعمدة ورقة التاريخ تماماً."""
    handle = _create_mock_handle()
    ws_mock = MagicMock()
    handle.spreadsheet.worksheet.return_value = ws_mock

    row_data = {
        "time": "2026-11-18T20:00:00Z",
        "ounce_usd": 3740.0,
        "usd_egp": 53.72,
        "usd_source": "fawazahmed0",
        "buy_24k": 6550.0,
        "sell_24k": 6600.0,
        "sell_21k": 5775.0,
        "sell_18k": 4950.0,
        "calculated_14k": 3850.0,
        "gold_pound_sell": 46200.0,
        "fair_24k": 6450.0,
        "gap_egp": 150.0,
        "gap_pct": 2.3,
        "status": "higher",
        "action": "alert",
        "change_pct": 0.5,
    }

    append_history(handle, row_data)

    assert ws_mock.append_row.call_count == 1
    call_args, call_kwargs = ws_mock.append_row.call_args
    appended_list = call_args[0]

    assert len(appended_list) == len(HISTORY_COLUMNS)
    for idx, col_name in enumerate(HISTORY_COLUMNS):
        assert appended_list[idx] == row_data[col_name]


@patch("gold_radar.sheets_store.time.sleep")
@patch("gold_radar.sheets_store.Credentials.from_service_account_info")
@patch("gold_radar.sheets_store.gspread.authorize")
def test_failure_never_leaks_secrets(mock_auth, mock_creds, mock_sleep):
    """في جميع حالات الفشل، التأكد الصارم من عدم ظهور JSON أو المفتاح الخاص أو معرف الجدول في الخطأ."""
    # 1. فشل open_store
    mock_client = MagicMock()
    mock_auth.return_value = mock_client
    mock_client.open_by_key.side_effect = Exception(
        f"API Failure on sheet url https://docs.google.com/spreadsheets/d/{FAKE_SHEET_ID}/edit with key {FAKE_PRIVATE_KEY}"
    )

    with pytest.raises(RuntimeError) as exc_info:
        open_store(FAKE_SA_JSON, FAKE_SHEET_ID)

    err_text = str(exc_info.value)
    assert FAKE_SHEET_ID not in err_text
    assert FAKE_PRIVATE_KEY not in err_text
    assert FAKE_CLIENT_EMAIL not in err_text
    assert "https://docs.google.com" not in err_text

    # 2. فشل read_state
    handle = _create_mock_handle()
    handle.spreadsheet.worksheet.side_effect = Exception(f"Sheet error with id {FAKE_SHEET_ID}")
    with pytest.raises(RuntimeError) as exc_info:
        read_state(handle)
    assert FAKE_SHEET_ID not in str(exc_info.value)

    # 3. فشل write_state
    handle = _create_mock_handle()
    ws_mock = MagicMock()
    handle.spreadsheet.worksheet.return_value = ws_mock
    ws_mock.update.side_effect = Exception(f"Write error for sheet {FAKE_SHEET_ID}")
    with pytest.raises(RuntimeError) as exc_info:
        write_state(handle, AlertState())
    assert FAKE_SHEET_ID not in str(exc_info.value)

    # 4. فشل append_history
    handle = _create_mock_handle()
    ws_mock = MagicMock()
    handle.spreadsheet.worksheet.return_value = ws_mock
    ws_mock.append_row.side_effect = Exception(f"Append error for sheet {FAKE_SHEET_ID}")
    with pytest.raises(RuntimeError) as exc_info:
        append_history(handle, {"time": "2026-11-18"})
    assert FAKE_SHEET_ID not in str(exc_info.value)
