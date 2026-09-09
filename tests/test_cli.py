from datetime import datetime, timezone
from pathlib import Path

import pytest

from pulse.__main__ import resolve_days, resolve_until
from pulse.db import open_session
from pulse.importer import import_path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def session(tmp_path):
    with open_session(str(tmp_path / "test.db")) as s:
        import_path(FIXTURES, s)
        yield s


def test_latest_comes_from_the_database(session):
    assert resolve_until("latest", session) == datetime(2026, 7, 19, 12, 15, tzinfo=timezone.utc)


def test_explicit_date_is_read_as_utc(session):
    assert resolve_until("2026-07-19", session) == datetime(2026, 7, 19, 0, 0, tzinfo=timezone.utc)


def test_explicit_date_with_an_offset_is_converted_not_overwritten(session):
    """Зсув зони треба перерахувати, а не затерти на +00:00.

    Затирання зсувало межу періоду на три години і втягувало у зріз пости,
    яких не просили.
    """
    assert resolve_until("2026-07-19T12:15:00+03:00", session) == datetime(
        2026, 7, 19, 9, 15, tzinfo=timezone.utc
    )


def test_default_is_now(session):
    # resolve_until обрізає мікросекунди, тому й межу порівняння обрізаємо
    before = datetime.now(timezone.utc).replace(microsecond=0)
    value = resolve_until(None, session)
    assert value >= before


def test_latest_on_empty_database_falls_back_to_now(tmp_path):
    with open_session(str(tmp_path / "empty.db")) as session:
        before = datetime.now(timezone.utc).replace(microsecond=0)
        assert resolve_until("latest", session) >= before


def test_unreadable_until_explains_itself(session):
    """Раніше сюди прилітав голий traceback від fromisoformat."""
    with pytest.raises(ValueError) as error:
        resolve_until("вчора", session)
    assert "вчора" in str(error.value)


def test_days_must_be_a_real_period():
    """--days=-5 мовчки давав перевернутий період і структурно валідні "0 постів":
    модель отримувала "даних немає" замість повідомлення про помилку."""
    with pytest.raises(ValueError):
        resolve_days(0)
    with pytest.raises(ValueError):
        resolve_days(-5)
    assert resolve_days(30) == 30


def test_import_of_a_missing_path_is_not_a_silent_success(tmp_path):
    with pytest.raises(ValueError) as error:
        with open_session(str(tmp_path / "t.db")) as session:
            import_path(tmp_path / "друкарська-помилка", session)
    assert "друкарська-помилка" in str(error.value)


def test_import_accepts_a_single_file(tmp_path):
    single = tmp_path / "one.csv"
    single.write_text(
        "\n".join([
            "post_id;Дата;Площадка;Текст;reach;Ссылка;Автор",
            "CRM-1;02.07.2026 12:40;TrafficDesk;текст;100;;автор",
        ]),
        encoding="utf-8",
    )
    with open_session(str(tmp_path / "t.db")) as session:
        summary = import_path(single, session)
    assert summary.stored == 1


def test_database_file_is_released_after_the_session(tmp_path):
    """На Windows незакритий Engine лишає файл бази заблокованим."""
    path = tmp_path / "released.db"
    with open_session(str(path)) as session:
        import_path(FIXTURES, session)
    path.unlink()
    assert not path.exists()
