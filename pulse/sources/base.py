"""Договір, який виконує кожен адаптер джерела."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from pulse.model import CanonicalPost


UNKNOWN_ZONE = "unknown"


def format_offset(value: datetime) -> str:
    """Зона оригіналу у вигляді, який видно очима: UTC, +03:00 або unknown.

    Naive значення означає, що зони в даних не було. Тоді підписувати результат
    як "UTC" — брехня: ані вихідна зона не UTC, ані перерахунку не відбулось.
    """
    offset = value.utcoffset()
    if offset is None:
        return UNKNOWN_ZONE
    if offset == timedelta(0):
        return "UTC"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return f"{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"


# line_number=0 означає "файл цілком", а не якийсь його рядок: так позначається
# випадок, коли файл не вдалося навіть відкрити чи розібрати.
WHOLE_FILE = 0


class Unreadable(Exception):
    """Значення прочитати не вдалося. Рядок піде в rejected_rows із цією причиною."""


def reason_of(error: Exception) -> str:
    """Причина відмови у вигляді, придатному для очей людини."""
    if isinstance(error, Unreadable):
        return str(error)
    return f"{type(error).__name__}: {error}"


@dataclass
class Rejected:
    """Рядок, який не вдалося прочитати. Достатньо, щоб знайти його очима."""

    source_file: str
    line_number: int
    reason: str
    raw: str


@dataclass
class ParseResult:
    posts: list[CanonicalPost] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)


class SourceAdapter(Protocol):
    """Адаптер знає лише свій формат.

    Він не знає, що існує база, і не знає про інші джерела.
    Вид метрики оголошується тут один раз, а не пишеться в кожен пост.
    """

    name: str                      # потрапляє в CanonicalPost.source
    metric_name: str | None        # "views" / "reach" / None
    metric_precision: str | None   # "rounded" / "exact" / None

    def can_handle(self, path: Path) -> bool: ...

    def parse(self, path: Path) -> ParseResult: ...
