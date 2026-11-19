"""
عميل تيليجرام لإرسال التنبيهات (src/gold_radar/telegram_client.py).
لمشروع مرصاد الذهب (Gold Radar).

يرسل الرسائل كنص عادي (Plain text) بدون parse_mode، مع إعادة المحاولة
فقط عند أخطاء الشبكة، 5xx، و 429 (مع احترام retry_after بحد أقصى).
أمان صارم: إخفاء التوكن ومعرف المحادثة تماماً من أي رسائل خطأ أو استثناءات (raise ... from None).
"""

import time
import requests

from gold_radar.config import (
    RETRY_BACKOFF_FACTOR,
    TELEGRAM_MAX_MESSAGE_LENGTH,
    TELEGRAM_MAX_RETRIES,
    TELEGRAM_MAX_RETRY_AFTER_SECONDS,
    TELEGRAM_TIMEOUT_SECONDS,
    USER_AGENT,
)


def send_message(text: str, token: str, chat_id: str) -> None:
    """
    إرسال رسالة نصية عبر Telegram Bot API:
    - التحقق من صلاحية النص وطوله (<= 4096).
    - عدم استخدام parse_mode (نص عادي).
    - حماية تامة للأسرار: منع تسريب التوكن أو chat_id في أي رسالة خطأ أو Traceback.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("نص رسالة تيليجرام فارغ أو غير صالح")

    if len(text) > TELEGRAM_MAX_MESSAGE_LENGTH:
        raise ValueError(
            f"طول رسالة تيليجرام ({len(text)} حرفاً) يتجاوز الحد الأقصى المسموح ({TELEGRAM_MAX_MESSAGE_LENGTH} حرفاً)"
        )

    clean_token = token.strip() if isinstance(token, str) else ""
    if not clean_token:
        raise ValueError("رمز بوت تيليجرام (Token) مفقود أو فارغ")

    clean_chat_id = chat_id.strip() if isinstance(chat_id, str) else ""
    if not clean_chat_id:
        raise ValueError("معرف محادثة تيليجرام (Chat ID) مفقود أو فارغ")

    # تكوين رابط الطلب والبيانات
    url = f"https://api.telegram.org/bot{clean_token}/sendMessage"
    payload = {
        "chat_id": clean_chat_id,
        "text": text,
    }
    headers = {"User-Agent": USER_AGENT}

    for attempt in range(1, TELEGRAM_MAX_RETRIES + 1):
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=TELEGRAM_TIMEOUT_SECONDS,
            )

            # نجاح الطلب
            if response.status_code == 200:
                return

            # حالة الضغط وتجاوز المعدل (HTTP 429 Too Many Requests)
            if response.status_code == 429:
                retry_after = 1.0
                try:
                    res_json = response.json()
                    retry_after = float(res_json.get("parameters", {}).get("retry_after", 1.0))
                except Exception:
                    pass

                wait_time = min(max(retry_after, 0.5), float(TELEGRAM_MAX_RETRY_AFTER_SECONDS))

                if attempt < TELEGRAM_MAX_RETRIES:
                    time.sleep(wait_time)
                    continue

                raise RuntimeError(
                    f"فشل إرسال رسالة تيليجرام بسبب كثرة الطلبات (429) بعد {TELEGRAM_MAX_RETRIES} محاولات"
                ) from None

            # أخطاء الخادم (HTTP 5xx)
            if response.status_code >= 500:
                if attempt < TELEGRAM_MAX_RETRIES:
                    sleep_time = RETRY_BACKOFF_FACTOR * (2 ** (attempt - 1))
                    time.sleep(sleep_time)
                    continue

                raise RuntimeError(
                    f"فشل إرسال رسالة تيليجرام بسبب خطأ في خوادم تيليجرام (كود {response.status_code}) بعد {TELEGRAM_MAX_RETRIES} محاولات"
                ) from None

            # أخطاء العميل الأخرى (مثل 400 Bad Request أو 403 Forbidden) - لا يعاد المحاولة
            error_desc = "خطأ في المعاملات"
            try:
                raw_desc = response.json().get("description", "")
                # تنظيف أي احتمال لظهور التوكن أو المعرف في نص الخطأ العائد
                error_desc = raw_desc.replace(clean_token, "[REDACTED]").replace(clean_chat_id, "[REDACTED]")
            except Exception:
                pass

            raise RuntimeError(
                f"رفض تيليجرام إرسال الرسالة بكود {response.status_code}: {error_desc}"
            ) from None

        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt < TELEGRAM_MAX_RETRIES:
                sleep_time = RETRY_BACKOFF_FACTOR * (2 ** (attempt - 1))
                time.sleep(sleep_time)
                continue

            raise RuntimeError(
                f"تعذر الاتصال بخوادم تيليجرام بعد {TELEGRAM_MAX_RETRIES} محاولات (انقطاع اتصال أو انتهاء المهلة)"
            ) from None

        except requests.RequestException:
            raise RuntimeError("حدث خطأ أثناء محاولة الاتصال بشبكة تيليجرام") from None
