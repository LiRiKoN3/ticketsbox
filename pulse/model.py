"""Канонічна форма поста — єдина, до якої зводяться всі джерела."""

from dataclasses import dataclass
from datetime import datetime

# Без цих полів запис не має сенсу: немає ключа, не потрапить у зріз,
# немає групи для аналітики. Решта може бути відсутня — це "немає даних".
REQUIRED_FIELDS = ("external_id", "channel", "published_at")


@dataclass(frozen=True)
class CanonicalPost:
    source: str                      # telegram / rss / crm_csv
    external_id: str                 # унікальний у межах свого джерела
    channel: str                     # канал або стрічка всередині джерела
    published_at: datetime           # завжди tz-aware UTC
    source_timezone: str             # зона, з якої перерахували
    text: str | None = None
    metric_value: int | None = None  # None = даних немає, ніколи не 0
    url: str | None = None
    is_forward: bool | None = None   # None = джерело такого поняття не має


def missing_required(values: dict) -> list[str]:
    """Повертає імена обов'язкових полів, яких бракує або які порожні."""
    return [name for name in REQUIRED_FIELDS if not values.get(name)]
