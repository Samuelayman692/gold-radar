"""
نماذج البيانات لطبقة المصادر (src/gold_radar/sources/models.py).
كائنات بيانات بسيطة (dataclasses) مع توقيتات موحدة بتوقيت UTC.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OuncePrice:
    """سعر أونصة الذهب العالمي بالدولار."""
    usd: float
    fetched_at: datetime


@dataclass(frozen=True)
class UsdRate:
    """سعر صرف الدولار مقابل الجنيه المصري."""
    rate: float
    source_name: str
    fetched_at: datetime


@dataclass(frozen=True)
class LocalPrices:
    """أسعار الذهب المحلية في السوق المصري (شراء وبيع)."""
    buy_24k: float
    sell_24k: float
    buy_21k: float
    sell_21k: float
    buy_18k: float
    sell_18k: float
    buy_pound: float
    sell_pound: float
    fetched_at: datetime
