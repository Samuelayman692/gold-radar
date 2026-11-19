"""
اختبارات وحدة عميل تيليجرام (tests/test_telegram_client.py)
لمشروع مرصاد الذهب (Gold Radar).

اختبارات نقية بالكامل باستخدام المحاكاة (Mocking) وبدون أي اتصالات شبكية حقيقية:
- نجاح الإرسال والتحقق من عدم استخدام parse_mode
- استجابة 429 متبوعة بنجاح الإرسال بعد الانتظار
- استجابات 5xx وإعادة المحاولة ثم الفشل بعد استنفاد المحاولات
- استجابة 400 والتأكد من عدم إعادة المحاولة
- خطأ الشبكة والتحقق الصارم من عدم تسريب التوكن أو المعرف في أي خطأ
- رفض النصوص الفارغة أو التي تتجاوز 4096 حرفاً
"""

from unittest.mock import MagicMock, patch
import sys
from pathlib import Path
import pytest
import requests

# إضافة مجلد src لمسار الحزم
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gold_radar.telegram_client import send_message

FAKE_TOKEN = "999999999:AAFakeTokenSecretKey_DoNotLeakMe123456"
FAKE_CHAT_ID = "1234567890_SECRET_CHAT_ID"


@patch("gold_radar.telegram_client.requests.post")
def test_send_message_success(mock_post):
    """التحقق من نجاح إرسال الرسالة كنص عادي وعدم وجود parse_mode."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True}
    mock_post.return_value = mock_resp

    send_message("رسالة اختبار ناجحة", FAKE_TOKEN, FAKE_CHAT_ID)

    assert mock_post.call_count == 1
    call_args, call_kwargs = mock_post.call_args

    # التحقق من أن الرابط يحتوي على البوت
    assert f"bot{FAKE_TOKEN}" in call_args[0]

    # التحقق من أن البيانات نص عادي تماماً وبدون parse_mode
    json_payload = call_kwargs["json"]
    assert json_payload["chat_id"] == FAKE_CHAT_ID
    assert json_payload["text"] == "رسالة اختبار ناجحة"
    assert "parse_mode" not in json_payload


@patch("gold_radar.telegram_client.time.sleep")
@patch("gold_radar.telegram_client.requests.post")
def test_send_message_429_then_success(mock_post, mock_sleep):
    """استجابة 429 ثم نجاح في المحاولة الثانية مع احترام retry_after."""
    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.json.return_value = {"parameters": {"retry_after": 2}}

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {"ok": True}

    mock_post.side_effect = [resp_429, resp_200]

    send_message("تجربة بعد 429", FAKE_TOKEN, FAKE_CHAT_ID)

    assert mock_post.call_count == 2
    mock_sleep.assert_called_once_with(2.0)


@patch("gold_radar.telegram_client.time.sleep")
@patch("gold_radar.telegram_client.requests.post")
def test_send_message_5xx_retries_and_fails(mock_post, mock_sleep):
    """أخطاء 5xx يعاد المحاولة فيها 3 مرات ثم ترفع خطأ آمناً دون تسريب التوكن أو المعرف."""
    resp_502 = MagicMock()
    resp_502.status_code = 502

    mock_post.return_value = resp_502

    with pytest.raises(RuntimeError) as exc_info:
        send_message("تجربة خطأ خادم", FAKE_TOKEN, FAKE_CHAT_ID)

    # التحقق من عدد المحاولات (3 مرات)
    assert mock_post.call_count == 3
    err_text = str(exc_info.value)

    # أمان تام: التحقق من عدم تسريب التوكن أو المعرف
    assert FAKE_TOKEN not in err_text
    assert FAKE_CHAT_ID not in err_text


@patch("gold_radar.telegram_client.requests.post")
def test_send_message_400_not_retried(mock_post):
    """خطأ 400 (Bad Request) لا يعاد المحاولة فيه إطلاقاً."""
    resp_400 = MagicMock()
    resp_400.status_code = 400
    resp_400.json.return_value = {"description": "Bad Request: chat not found"}
    mock_post.return_value = resp_400

    with pytest.raises(RuntimeError) as exc_info:
        send_message("تجربة خطأ 400", FAKE_TOKEN, FAKE_CHAT_ID)

    # طلب واحد فقط دون إعادة محاولة
    assert mock_post.call_count == 1
    err_text = str(exc_info.value)

    # فحص الأمان
    assert FAKE_TOKEN not in err_text
    assert FAKE_CHAT_ID not in err_text


@patch("gold_radar.telegram_client.time.sleep")
@patch("gold_radar.telegram_client.requests.post")
def test_send_message_network_error_safe(mock_post, mock_sleep):
    """انقطاع الاتصال بالشبكة يرفع خطأ آمناً بالعربية ولا يسرب التوكن أو الرابط في الاستثناء."""
    # محاكاة خطأ يحتوي على الرابط والتوكن
    dangerous_error = requests.ConnectionError(
        f"Failed to establish connection: https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage"
    )
    mock_post.side_effect = dangerous_error

    with pytest.raises(RuntimeError) as exc_info:
        send_message("تجربة انقطاع شبكة", FAKE_TOKEN, FAKE_CHAT_ID)

    assert mock_post.call_count == 3

    # فحص نص الخطأ
    err_text = str(exc_info.value)
    assert FAKE_TOKEN not in err_text
    assert FAKE_CHAT_ID not in err_text
    assert "api.telegram.org" not in err_text

    # التحقق من كتم الاستثناء الأصلي بواسطة (raise ... from None)
    assert exc_info.value.__cause__ is None


@pytest.mark.parametrize("empty_txt", ["", "   ", None])
def test_send_message_empty_text_raises_value_error(empty_txt):
    """النصوص الفارغة ترفع خطأ ValueError فوراً دون إرسال طلب."""
    with pytest.raises(ValueError, match="فارغ"):
        send_message(empty_txt, FAKE_TOKEN, FAKE_CHAT_ID)


def test_send_message_too_long_raises_value_error():
    """النصوص التي تتجاوز 4096 حرفاً ترفع ValueError فوراً."""
    too_long_text = "أ" * 4097
    with pytest.raises(ValueError, match="يتجاوز الحد الأقصى"):
        send_message(too_long_text, FAKE_TOKEN, FAKE_CHAT_ID)


def test_send_message_missing_token_or_chat_id():
    """فقدان التوكن أو المعرف يرفع ValueError فوراً."""
    with pytest.raises(ValueError, match="Token"):
        send_message("نص", "", FAKE_CHAT_ID)

    with pytest.raises(ValueError, match="Chat ID"):
        send_message("نص", FAKE_TOKEN, "")
