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


def resolve_until(value: str | None, session) -> datetime:
    """None -> зараз. "latest" -> найсвіжіший пост у базі. Інакше — дата ISO."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if value is None:
        return now
    if value == "latest":
        return newest_published_at(session) or now
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


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

    if args.command == "import":
        with open_session(args.db) as session:
            summary = import_path(args.path, session)
        print(f"прочитано постів: {summary.imported}")
        for name, count in sorted(summary.by_source.items()):
            print(f"  {name}: {count}")
        print(f"відкинуто рядків: {summary.rejected}")

    if args.command == "report":
        with open_session(args.db) as session:
            until = resolve_until(args.until, session)
            report = build_report(session, days=args.days, until=until)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
