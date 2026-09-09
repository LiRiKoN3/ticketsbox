"""Командний рядок.

    python -m pulse import fixtures/
    python -m pulse report --days=30 --until=latest
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from pulse.db import newest_published_at, open_session
from pulse.importer import import_path
from pulse.report import build_report

DEFAULT_DB = "pulse.db"


def resolve_days(value: int) -> int:
    """Період має бути додатним.

    Від'ємне значення давало перевернутий період (from > to) і структурно
    валідні "0 постів" — модель отримувала "даних немає" замість помилки.
    """
    if value <= 0:
        raise ValueError(f"--days має бути додатним числом, а не {value}")
    return value


def resolve_until(value: str | None, session) -> datetime:
    """None -> зараз. "latest" -> найсвіжіший пост у базі. Інакше — дата ISO."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if value is None:
        return now
    if value == "latest":
        return newest_published_at(session) or now

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(
            f'не розумію дату "{value}": чекаю на ISO (2026-07-19 або '
            f'2026-07-19T12:15:00+03:00) чи на слово latest'
        ) from None

    if parsed.tzinfo is None:
        # Дата без зони — домовленість: вважаємо її UTC. Це тлумачення введеного
        # користувачем, а не перетворення для зберігання (див. UtcDateTime).
        return parsed.replace(tzinfo=timezone.utc)
    # Зона вказана — її треба перерахувати, а не затерти.
    return parsed.astimezone(timezone.utc)


def run_import(args) -> None:
    with open_session(args.db) as session:
        summary = import_path(args.path, session)
    print(f"прочитано постів: {summary.imported}")
    for name, count in sorted(summary.by_source.items()):
        print(f"  {name}: {count}")
    print(f"збережено в базі: {summary.stored}")
    print(f"відкинуто рядків: {summary.rejected}")
    for failure in summary.failed_files:
        print(f"файл не опрацьовано: {failure}")


def run_report(args) -> None:
    with open_session(args.db) as session:
        report = build_report(
            session, days=resolve_days(args.days), until=resolve_until(args.until, session)
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    # Консоль Windows часто працює в кодуванні, де українських літер немає
    # (cp1252, cp866). Без цього рядка звичайний print падає з UnicodeEncodeError
    # на чужій машині, хоча на нашій усе зелене.
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="pulse")
    parser.add_argument("--db", default=DEFAULT_DB)
    commands = parser.add_subparsers(dest="command", required=True)

    import_command = commands.add_parser("import", help="прочитати теку з даними")
    import_command.add_argument("path", type=Path)

    report_command = commands.add_parser("report", help="зріз за період")
    report_command.add_argument("--days", type=int, default=30)
    report_command.add_argument(
        "--until", default=None,
        help='кінець періоду: дата ISO або "latest" (найсвіжіший пост у базі)',
    )

    args = parser.parse_args()

    # Помилка у вводі — це зрозумілий рядок і код виходу, а не голий traceback.
    try:
        if args.command == "import":
            run_import(args)
        if args.command == "report":
            run_report(args)
    except ValueError as error:
        print(f"помилка: {error}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
