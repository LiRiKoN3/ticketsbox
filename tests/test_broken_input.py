"""Бруд виду «поле є, але воно сміття».

Механізм Rejected спочатку вмів лише «поля немає». Найімовірніший бруд має
іншу форму, і на ньому імпорт падав, забираючи з собою все прочитане раніше.

Правило, яке перевіряють ці тести:
  - нечитабельне обов'язкове поле  -> рядок відкидається з причиною;
  - нечитабельне необов'язкове     -> рядок лишається, поле стає None;
  - нечитабельний файл цілком      -> відкидається файл, решта читається далі.
"""

import pytest

from pulse.db import all_posts, open_session
from pulse.importer import import_path
from pulse.sources.crm_csv import CrmCsvAdapter
from pulse.sources.rss import RssAdapter
from pulse.sources.telegram import TelegramAdapter

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Broken Feed</title>
  <link>https://broken.example</link>
  <item>
    <title>Придатний</title>
    <guid isPermaLink="false">ok-1</guid>
    <pubDate>Wed, 01 Jul 2026 12:00:00 +0300</pubDate>
  </item>
  <item>
    <title>Дата нісенітниця</title>
    <guid isPermaLink="false">bad-1</guid>
    <pubDate>19 lypnia 2026</pubDate>
  </item>
</channel></rss>
"""

TELEGRAM_PAGE = """<html><body>
<div class="tgme_widget_message" data-post="chan/1">
  <time datetime="2026-07-02T08:05:00+00:00"></time>
  <span class="tgme_widget_message_views">12K views</span>
</div>
<div class="tgme_widget_message" data-post="chan/2">
  <time datetime="01 July 2026"></time>
</div>
</body></html>
"""

CSV_HEADER = "post_id;Дата;Площадка;Текст;reach;Ссылка;Автор\n"


def write(tmp_path, name, text, encoding="utf-8"):
    path = tmp_path / name
    path.write_text(text, encoding=encoding)
    return path


# --- RSS ------------------------------------------------------------------

def test_unreadable_date_rejects_only_that_item(tmp_path):
    result = RssAdapter().parse(write(tmp_path, "feed.xml", FEED))
    assert len(result.posts) == 1
    assert result.posts[0].external_id.endswith("ok-1")
    assert len(result.rejected) == 1
    assert "19 lypnia 2026" in result.rejected[0].raw


def test_truncated_xml_is_rejected_not_raised(tmp_path):
    result = RssAdapter().parse(write(tmp_path, "cut.xml", FEED[: len(FEED) // 2]))
    assert result.posts == []
    assert len(result.rejected) == 1


def test_feed_without_channel_is_rejected_not_raised(tmp_path):
    naked = '<?xml version="1.0"?><rss version="2.0"></rss>'
    result = RssAdapter().parse(write(tmp_path, "naked.xml", naked))
    assert result.posts == []
    assert len(result.rejected) == 1


# --- Telegram -------------------------------------------------------------

def test_unreadable_datetime_attribute_rejects_only_that_post(tmp_path):
    result = TelegramAdapter().parse(write(tmp_path, "page.html", TELEGRAM_PAGE))
    assert [p.external_id for p in result.posts] == ["chan/1"]
    assert len(result.rejected) == 1


def test_unreadable_views_leave_the_post_without_a_metric(tmp_path):
    result = TelegramAdapter().parse(write(tmp_path, "page.html", TELEGRAM_PAGE))
    assert result.posts[0].metric_value is None


# --- CRM CSV --------------------------------------------------------------

def test_csv_in_another_encoding_is_rejected_not_raised(tmp_path):
    path = tmp_path / "cp1251.csv"
    path.write_bytes("post_id;Дата;Площадка\nCRM-1;02.07.2026 12:40;Телеграм\n".encode("cp1251"))
    result = CrmCsvAdapter().parse(path)
    assert result.posts == []
    assert len(result.rejected) == 1


def test_unreadable_reach_leaves_the_post_without_a_metric(tmp_path):
    body = CSV_HEADER + "CRM-1;02.07.2026 12:40;TrafficDesk;текст;²;;автор\n"
    result = CrmCsvAdapter().parse(write(tmp_path, "dirty.csv", body))
    assert len(result.posts) == 1
    assert result.posts[0].metric_value is None


def test_unreadable_date_rejects_the_csv_row(tmp_path):
    body = CSV_HEADER + "CRM-1;19 lypnia 2026;TrafficDesk;текст;100;;автор\n"
    result = CrmCsvAdapter().parse(write(tmp_path, "dirty.csv", body))
    assert result.posts == []
    assert len(result.rejected) == 1


# --- імпорт цілком --------------------------------------------------------

def test_one_broken_file_does_not_lose_the_others(tmp_path):
    """Найголовніше: побитий файл не забирає з собою те, що вже прочитано."""
    data = tmp_path / "data"
    data.mkdir()
    (data / "good.csv").write_text(
        CSV_HEADER + "CRM-1;02.07.2026 12:40;TrafficDesk;текст;100;;автор\n",
        encoding="utf-8",
    )
    (data / "zbroken.xml").write_text(FEED[: len(FEED) // 2], encoding="utf-8")

    with open_session(str(tmp_path / "t.db")) as session:
        import_path(data, session)
        assert [p.external_id for p in all_posts(session)] == ["CRM-1"]


# --- запобіжник на рівні обходу теки ----------------------------------------

def test_a_failing_file_does_not_lose_the_ones_read_before(tmp_path, monkeypatch):
    """Адаптери вже не падають, але впасти може й сховище (напр. завелика пачка).

    Прочитане до збою має лишитися в базі, а сам файл — потрапити у звіт
    як необроблений, а не зникнути мовчки.
    """
    import pulse.importer as importer

    data = tmp_path / "data"
    data.mkdir()
    (data / "a_good.csv").write_text(
        CSV_HEADER + "CRM-GOOD;02.07.2026 12:40;TrafficDesk;текст;100;;автор\n",
        encoding="utf-8",
    )
    (data / "b_bad.csv").write_text(
        CSV_HEADER + "CRM-BAD;03.07.2026 12:40;TrafficDesk;текст;100;;автор\n",
        encoding="utf-8",
    )

    real_save = importer.save_posts

    def flaky(session, posts):
        if posts and posts[0].external_id == "CRM-BAD":
            raise RuntimeError("сховище відмовило")
        return real_save(session, posts)

    monkeypatch.setattr(importer, "save_posts", flaky)

    with open_session(str(tmp_path / "t.db")) as session:
        summary = import_path(data, session)
        assert [p.external_id for p in all_posts(session)] == ["CRM-GOOD"]
        assert len(summary.failed_files) == 1
        assert "b_bad.csv" in summary.failed_files[0]


# --- зона, якої в даних немає -----------------------------------------------

NO_ZONE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Zoneless</title>
  <link>https://zoneless.example</link>
  <item>
    <guid isPermaLink="false">z-1</guid>
    <pubDate>Wed, 01 Jul 2026 12:00:00 -0000</pubDate>
  </item>
</channel></rss>
"""

TELEGRAM_WITH_OFFSET = """<html><body>
<div class="tgme_widget_message" data-post="chan/9">
  <time datetime="2026-07-02T11:05:00+03:00"></time>
</div>
</body></html>
"""


def test_date_without_a_zone_is_not_read_in_the_machine_zone(tmp_path):
    """-0000 у RFC 822 означає "зона невідома", і datetime приходить naive.

    Далі .astimezone() підставляв зону процесу, тож published_at залежав від
    комп'ютера, а підпис усе одно казав "UTC".
    """
    result = RssAdapter().parse(write(tmp_path, "z.xml", NO_ZONE_FEED))
    post = result.posts[0]
    assert post.published_at.hour == 12
    assert post.source_timezone == "unknown"


def test_telegram_reports_the_offset_it_actually_saw(tmp_path):
    """Підпис "UTC" був зашитий незалежно від того, що стоїть в атрибуті."""
    result = TelegramAdapter().parse(write(tmp_path, "p.html", TELEGRAM_WITH_OFFSET))
    post = result.posts[0]
    assert post.published_at.hour == 8
    assert post.source_timezone == "+03:00"


def test_a_failing_file_reaches_the_report_not_only_the_console(tmp_path, monkeypatch):
    """Файл, який не записався цілком, мусить дійти до контракту.

    Інакше модель бачить уламок даних і не має способу про це дізнатись:
    posts_total показує те, що вціліло, а rejected_on_import — нуль.
    """
    import pulse.importer as importer
    from pulse.db import count_rejected

    data = tmp_path / "data"
    data.mkdir()
    (data / "a_good.csv").write_text(
        CSV_HEADER + "CRM-GOOD;02.07.2026 12:40;TrafficDesk;текст;100;;автор" + chr(10),
        encoding="utf-8",
    )
    (data / "b_bad.csv").write_text(
        CSV_HEADER + "CRM-BAD;03.07.2026 12:40;TrafficDesk;текст;100;;автор" + chr(10),
        encoding="utf-8",
    )

    real_save = importer.save_posts

    def flaky(session, posts):
        if posts and posts[0].external_id == "CRM-BAD":
            raise RuntimeError("x" * 5000)      # довжелезний текст помилки
        return real_save(session, posts)

    monkeypatch.setattr(importer, "save_posts", flaky)

    with open_session(str(tmp_path / "t.db")) as session:
        summary = import_path(data, session)
        assert count_rejected(session) == 1
        assert len(summary.failed_files[0]) < 500     # текст помилки обрізано
