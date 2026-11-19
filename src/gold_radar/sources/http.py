"""
مساعد طلبات HTTP للشبكة (src/gold_radar/sources/http.py).
يوفر دالة موحدة لتنفيذ طلبات GET مع مهلة انتظار، إعادة محاولة محدودة،
ترويسة مهذبة، ورسائل خطأ واضحة باللغة العربية مع إخفاء أي معلمات حساسة من الروابط.
"""

import time
from urllib.parse import urlparse
import requests

from gold_radar.config import MAX_RETRIES, NETWORK_TIMEOUT_SECONDS, RETRY_BACKOFF_FACTOR, USER_AGENT


def sanitize_url(url: str) -> str:
    """تنظيف الرابط من أي معلمات استعلام (query parameters) لتجنب تسريب أي أسرار في السجلات."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def http_get(
    url: str,
    headers: dict | None = None,
    timeout: int = NETWORK_TIMEOUT_SECONDS,
    max_retries: int = MAX_RETRIES,
) -> requests.Response:
    """
    تنفيذ طلب HTTP GET آمن ومهذب مع إعادة المحاولة ومعالجة الأخطاء.
    """
    safe_url = sanitize_url(url)
    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)

    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=req_headers, timeout=timeout)
            
            # إذا كان الطلب ناجحاً
            if response.status_code == 200:
                return response

            # أخطاء الخادم أو الضغط المؤقت (5xx أو 429) تستحق إعادة المحاولة
            if response.status_code in (429, 500, 502, 503, 504):
                if attempt < max_retries:
                    sleep_time = RETRY_BACKOFF_FACTOR * (2 ** (attempt - 1))
                    time.sleep(sleep_time)
                    continue
                raise RuntimeError(
                    f"فشل الطلب من '{safe_url}' بعد {max_retries} محاولات، كود الحالة: {response.status_code}"
                )

            # أخطاء العميل الأخرى (مثل 403 أو 404) لا نعيد المحاولة فيها
            raise RuntimeError(
                f"فشل الطلب من '{safe_url}' بكود الحالة {response.status_code}"
            )

        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt < max_retries:
                sleep_time = RETRY_BACKOFF_FACTOR * (2 ** (attempt - 1))
                time.sleep(sleep_time)
                continue
            raise RuntimeError(
                f"تعذر الاتصال بـ '{safe_url}' بعد {max_retries} محاولات: خطأ اتصال أو انتهاء المهلة ({exc.__class__.__name__})"
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"خطأ أثناء طلب '{safe_url}': {exc}") from exc

    # احتياطياً في حال الخروج من الحلقة
    raise RuntimeError(f"فشل الاتصال بـ '{safe_url}': {last_error}")
