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


def test_summary_separates_what_was_read_from_what_was_stored(session):
    """CLI рапортував прочитане так, ніби це збережене, і розбіжність ховалась."""
    summary = import_path(FIXTURES, session)
    assert summary.imported == 60      # прочитано з файлів
    assert summary.stored == 59        # лягло в базу після схлопування за ключем


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


FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>{title}</title>
  <link>{link}</link>
  <item>
    <title>Той самий номер, інша стрічка</title>
    <guid isPermaLink="false">1</guid>
    <pubDate>Wed, 01 Jul 2026 12:00:00 +0000</pubDate>
  </item>
</channel></rss>
"""


def test_two_feeds_with_the_same_guid_do_not_overwrite_each_other(tmp_path):
    """RSS вимагає унікальності guid лише в межах стрічки.

    Дослівний guid як ключ означав, що пост однієї стрічки мовчки затирав
    пост іншої: у rejected_rows нічого, у CLI рапорт про успіх.
    """
    data = tmp_path / "data"
    data.mkdir()
    (data / "a.xml").write_text(
        FEED.format(title="Feed A", link="https://a.example"), encoding="utf-8"
    )
    (data / "b.xml").write_text(
        FEED.format(title="Feed B", link="https://b.example"), encoding="utf-8"
    )

    with open_session(str(tmp_path / "t.db")) as session:
        import_path(data, session)
        channels = sorted(p.channel for p in all_posts(session))
        assert channels == ["Feed A", "Feed B"]
