from pathlib import Path

import pytest
from sqlalchemy import select

from pulse.db import RejectedRow, all_posts, count_rejected, open_session
from pulse.importer import import_path

FIXTURES = Path("fixtures")


@pytest.fixture
def session(tmp_path):
    with open_session(str(tmp_path / "test.db")) as s:
        yield s


def test_import_reads_all_three_sources(session):
    summary = import_path(FIXTURES, session)
    assert summary.by_source == {"telegram": 25, "rss": 16, "crm_csv": 19}
    assert summary.rejected == 1


def test_duplicate_id_inside_one_file_collapses_to_one_row(session):
    import_path(FIXTURES, session)
    rows = [p for p in all_posts(session) if p.external_id == "CRM-04102"]
    assert len(rows) == 1
    assert rows[0].metric_value == 8430      # виграє останній прочитаний рядок


def test_total_stored_posts(session):
    import_path(FIXTURES, session)
    assert len(all_posts(session)) == 59


def test_second_import_creates_no_duplicates(session):
    import_path(FIXTURES, session)
    first = len(all_posts(session))
    import_path(FIXTURES, session)
    assert len(all_posts(session)) == first
    assert count_rejected(session) == 1


def test_rejected_row_is_findable(session):
    import_path(FIXTURES, session)
    row = session.scalars(select(RejectedRow)).one()
    assert row.source_file.endswith("export.csv")
    assert row.line_number == 12
