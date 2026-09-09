"""Адаптер вивантаження з чужої CRM. Найбрудніше джерело."""

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from pulse.model import CanonicalPost, missing_required
from pulse.sources.base import WHOLE_FILE, ParseResult, Rejected, reason_of

KYIV = ZoneInfo("Europe/Kyiv")
COLUMNS = 7                       # post_id;Дата;Площадка;Текст;reach;Ссылка;Автор
DATE_FORMATS = ("%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M")
SPACES = re.compile(r"\s")   # \s у Python ловить і нерозривний пробіл
# Кома як роздільник тисяч — лише коли вона групує рівно по три цифри.
# "1,5" під це не підпадає і числом не вважається: краще None, ніж вигадка.
THOUSANDS = re.compile(r"^-?\d{1,3}(,\d{3})+$")


def parse_number(raw: str) -> int | None:
    """"2 436" -> 2436. Порожнє і "n/a" -> None, ніколи не 0."""
    # Через int(), а не через isdigit(): останній вважає числом "²"
    # (на якому int потім падає) і не вважає числом "-42".
    value = SPACES.sub("", raw or "")
    if THOUSANDS.match(value):
        value = value.replace(",", "")
    try:
        return int(value)
    except ValueError:
        return None


def parse_kyiv_datetime(raw: str) -> datetime | None:
    """У вивантаженні два формати дат і жодної зони. Вважаємо київським часом.

    Перерахунок іде через назву зони, а не через фіксований зсув:
    влітку Київ це +3, взимку +2.
    """
    value = (raw or "").strip()
    for fmt in DATE_FORMATS:
        try:
            naive = datetime.strptime(value, fmt)
        except ValueError:
            continue
        return naive.replace(tzinfo=KYIV).astimezone(timezone.utc)
    return None


class CrmCsvAdapter:
    name = "crm_csv"
    metric_name = "reach"          # охоплення, не перегляди
    metric_precision = "exact"

    def can_handle(self, path: Path) -> bool:
        return path.suffix == ".csv"

    def parse(self, path: Path) -> ParseResult:
        result = ParseResult()
        try:
            self._read_rows(path, result)
        except (OSError, UnicodeDecodeError, csv.Error) as error:
            # Чуже кодування або побитий файл — відмова файлу, не всього імпорту.
            result.rejected.append(Rejected(str(path), WHOLE_FILE, reason_of(error), ""))
        return result

    def _read_rows(self, path: Path, result: ParseResult) -> None:
        # utf-8-sig прибирає BOM на початку файлу
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter=";")
            for number, row in enumerate(reader, start=1):
                if number == 1:
                    continue                       # заголовок
                if not any(cell.strip() for cell in row):
                    result.rejected.append(
                        Rejected(str(path), number, "порожній рядок", ";".join(row))
                    )
                    continue

                # У CRM-04107 бракує двох останніх колонок, але все потрібне на місці.
                # Доповнюємо порожніми, а придатність перевіряємо за полями, не за їх кількістю.
                row = row + [""] * (COLUMNS - len(row))
                post_id, raw_date, platform, text, reach, url, _author = row[:COLUMNS]

                values = {
                    "external_id": post_id.strip(),
                    "channel": platform.strip().lower(),
                    "published_at": parse_kyiv_datetime(raw_date),
                }
                absent = missing_required(values)
                if absent:
                    result.rejected.append(
                        Rejected(
                            str(path),
                            number,
                            f"бракує обов'язкових полів: {', '.join(absent)}",
                            ";".join(row),
                        )
                    )
                    continue

                result.posts.append(
                    CanonicalPost(
                        source=self.name,
                        external_id=values["external_id"],
                        channel=values["channel"],
                        published_at=values["published_at"],
                        source_timezone="Europe/Kyiv",
                        text=text.strip() or None,
                        metric_value=parse_number(reach),
                        url=url.strip() or None,   # ненадійне; не ключ і не привід зливати
                        is_forward=None,           # CRM такого поняття не має
                    )
                )
