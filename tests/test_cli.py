from datetime import datetime, timezone
from pathlib import Path

import pytest

from pulse.__main__ import resolve_until
from pulse.db import open_session
from pulse.importer import import_path

FIXTURES = Path("fixtures")


@pytest.fixture
def session(tmp_path):
    with open_session(str(tmp_path / "test.db")) as s:
        import_path(FIXTURES, s)
        yield s


def test_latest_comes_from_the_database(session):
    assert resolve_until("latest", session) == datetime(2026, 7, 19, 12, 15, tzinfo=timezone.utc)


def test_explicit_date_is_read_as_utc(session):
    assert resolve_until("2026-07-19", session) == datetime(2026, 7, 19, 0, 0, tzinfo=timezone.utc)


def test_default_is_now(session):
    # resolve_until обрізає мікросекунди, тому й межу порівняння обрізаємо
    before = datetime.now(timezone.utc).replace(microsecond=0)
    value = resolve_until(None, session)
    assert value >= before


def test_latest_on_empty_database_falls_back_to_now(tmp_path):
    with open_session(str(tmp_path / "empty.db")) as session:
        before = datetime.now(timezone.utc).replace(microsecond=0)
        assert resolve_until("latest", session) >= before
