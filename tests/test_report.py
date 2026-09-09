from datetime import datetime, timezone
from pathlib import Path

import pytest

from pulse.db import open_session
from pulse.importer import import_path
from pulse.report import build_report

FIXTURES = Path("fixtures")
UNTIL = datetime(2026, 7, 19, 12, 15, tzinfo=timezone.utc)


@pytest.fixture
def session(tmp_path):
    with open_session(str(tmp_path / "test.db")) as s:
        import_path(FIXTURES, s)
        yield s


def source_block(report, name):
    return next(s for s in report["sources"] if s["source"] == name)


def test_slice_describes_itself(session):
    report = build_report(session, days=30, until=UNTIL)
    assert report["slice"]["to"] == "2026-07-19T12:15:00+00:00"
    assert report["slice"]["from"] == "2026-06-19T12:15:00+00:00"
    assert report["slice"]["posts_total"] == 59
    assert report["slice"]["rejected_on_import"] == 1


def test_source_block_says_what_the_number_is(session):
    report = build_report(session, days=30, until=UNTIL)
    telegram = source_block(report, "telegram")
    assert telegram["metric"] == "views"
    assert telegram["metric_precision"] == "rounded"
    assert telegram["posts"] == 25
    assert telegram["with_metric"] == 23
    assert telegram["median"] == 14100


def test_source_without_metric_is_explicit(session):
    rss = source_block(build_report(session, days=30, until=UNTIL), "rss")
    assert rss["metric"] is None
    assert rss["with_metric"] == 0
    assert rss["median"] is None


def test_crm_numbers_are_after_deduplication(session):
    crm = source_block(build_report(session, days=30, until=UNTIL), "crm_csv")
    assert crm["metric"] == "reach"
    assert crm["posts"] == 18
    assert crm["with_metric"] == 16
    assert crm["median"] == 4543.5


def test_every_post_has_the_same_shape(session):
    posts = build_report(session, days=30, until=UNTIL)["posts"]
    keys = {frozenset(p.keys()) for p in posts}
    assert len(keys) == 1


def test_rss_post_has_explicit_nulls(session):
    posts = build_report(session, days=30, until=UNTIL)["posts"]
    rss_post = next(p for p in posts if p["source"] == "rss")
    assert rss_post["metric"] is None
    assert rss_post["vs_median"] is None
    assert rss_post["above_median"] is None
    assert rss_post["is_forward"] is None


def test_legend_is_present(session):
    report = build_report(session, days=30, until=UNTIL)
    assert "null" in report["legend"]
    assert "vs_median" in report["legend"]


def test_empty_slice_is_still_a_valid_report(session):
    """Раніше цей тест фіксував sources == [] як правильну поведінку.

    README обіцяє протилежне: структура лишається цілою — нулі в лічильниках
    і null у медіанах. Порожній список джерел не дає моделі відрізнити
    "за цей період нуль постів" від "такого джерела в нас немає".
    """
    report = build_report(session, days=1, until=datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert report["slice"]["posts_total"] == 0
    assert report["posts"] == []
    assert [s["source"] for s in report["sources"]] == ["crm_csv", "rss", "telegram"]
    for block in report["sources"]:
        assert block["posts"] == 0
        assert block["with_metric"] == 0
        assert block["median"] is None
    assert "legend" in report


def test_source_without_posts_in_the_period_keeps_its_block(session):
    report = build_report(session, days=3, until=UNTIL)
    telegram = source_block(report, "telegram")
    assert telegram["posts"] == 0
    assert telegram["median"] is None
    assert telegram["metric"] == "views"      # вид метрики оголошує адаптер


def test_source_gone_from_the_registry_does_not_break_the_report(session, monkeypatch):
    """Джерело перейменували в реєстрі, а накопичені дані лишились."""
    from pulse.sources.registry import ADAPTERS

    monkeypatch.setattr(
        "pulse.sources.registry.ADAPTERS",
        [a for a in ADAPTERS if a.name != "telegram"],
    )
    report = build_report(session, days=30, until=UNTIL)
    telegram = source_block(report, "telegram")
    assert telegram["posts"] == 25
    assert telegram["metric"] is None         # реєстр більше не знає, що це за число
