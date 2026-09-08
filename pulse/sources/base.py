"""Договір, який виконує кожен адаптер джерела."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pulse.model import CanonicalPost


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
