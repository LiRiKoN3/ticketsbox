from datetime import datetime, timezone

import pytest

from pulse.db import (all_posts, count_rejected, forget_rejected, open_session,
                      save_posts, save_rejected)
from pulse.model import CanonicalPost


def make_post(external_id="trafficdesk/1841", metric=3500, text="перший"):
    return CanonicalPost(
        source="telegram",
        external_id=external_id,
        channel="trafficdesk",
        published_at=datetime(2026, 7, 2, 8, 5, tzinfo=timezone.utc),
        source_timezone="UTC",
        text=text,
        metric_value=metric,
    )


@pytest.fixture
def session(tmp_path):
    with open_session(str(tmp_path / "test.db")) as s:
        yield s


def test_saving_same_post_twice_keeps_one_row(session):
    save_posts(session, [make_post()])
    save_posts(session, [make_post()])
    assert len(all_posts(session)) == 1


def test_second_save_updates_values(session):
    save_posts(session, [make_post(metric=3500, text="перший")])
    save_posts(session, [make_post(metric=4200, text="другий")])
    stored = all_posts(session)[0]
    assert stored.metric_value == 4200
    assert stored.text == "другий"


def test_duplicate_key_inside_one_batch_keeps_the_last(session):
    # у CSV той самий post_id трапляється двічі в одному файлі
    save_posts(session, [make_post(metric=1000, text="перший"),
                         make_post(metric=2000, text="другий")])
    stored = all_posts(session)
    assert len(stored) == 1
    assert stored[0].metric_value == 2000


def test_different_sources_with_same_id_are_different_rows(session):
    a = make_post(external_id="X-1")
    b = CanonicalPost(
        source="crm_csv",
        external_id="X-1",
        channel="trafficdesk",
        published_at=datetime(2026, 7, 2, 8, 5, tzinfo=timezone.utc),
        source_timezone="Europe/Kyiv",
    )
    save_posts(session, [a, b])
    assert len(all_posts(session)) == 2


def test_published_at_returns_as_utc_aware(session):
    save_posts(session, [make_post()])
    stored = all_posts(session)[0]
    assert stored.published_at.tzinfo is not None
    assert stored.published_at == datetime(2026, 7, 2, 8, 5, tzinfo=timezone.utc)


def test_none_metric_is_stored_as_null_not_zero(session):
    save_posts(session, [make_post(metric=None)])
    assert all_posts(session)[0].metric_value is None


class FakeRejected:
    def __init__(self):
        self.source_file = "fixtures/export.csv"
        self.line_number = 12
        self.reason = "порожній рядок"
        self.raw = ""


def test_rejected_rows_are_idempotent(session):
    save_rejected(session, [FakeRejected()])
    save_rejected(session, [FakeRejected()])
    assert count_rejected(session) == 1


def test_the_same_file_named_two_ways_is_one_file(session, tmp_path):
    """Шлях набирають по-різному, а файл той самий — рядок має бути один."""
    row = FakeRejected()
    row.source_file = str(tmp_path / "export.csv")
    save_rejected(session, [row])

    same = FakeRejected()
    same.source_file = str(tmp_path / "sub" / ".." / "export.csv")
    save_rejected(session, [same])

    assert count_rejected(session) == 1


def test_fixing_the_source_clears_its_old_rejected_rows(session):
    """Лічильник каже, наскільки зріз неповний. Виправили джерело —
    число має впасти, а не лишитися назавжди."""
    save_rejected(session, [FakeRejected()])
    forget_rejected(session, "fixtures/export.csv")
    save_rejected(session, [])
    assert count_rejected(session) == 0


def test_forgetting_one_file_does_not_touch_another(session):
    first = FakeRejected()
    second = FakeRejected()
    second.source_file = "fixtures/other.csv"
    save_rejected(session, [first, second])

    forget_rejected(session, "fixtures/export.csv")
    assert count_rejected(session) == 1
