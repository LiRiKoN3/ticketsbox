"""python -m pulse import fixtures/"""

import argparse
import sys
from pathlib import Path

from pulse.db import open_session
from pulse.importer import import_path

DEFAULT_DB = "pulse.db"


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

    args = parser.parse_args()

    if args.command == "import":
        with open_session(args.db) as session:
            summary = import_path(args.path, session)
        print(f"прочитано постів: {summary.imported}")
        for name, count in sorted(summary.by_source.items()):
            print(f"  {name}: {count}")
        print(f"відкинуто рядків: {summary.rejected}")


if __name__ == "__main__":
    main()
