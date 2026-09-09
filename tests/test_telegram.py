from datetime import datetime, timezone
from pathlib import Path

from pulse.sources.telegram import TelegramAdapter, parse_views

FIXTURES = Path("fixtures/telegram")


def parse(name):
    return TelegramAdapter().parse(FIXTURES / f"{name}.html")


def by_id(posts, external_id):
    return next(p for p in posts if p.external_id == external_id)


def test_parse_views_handles_thousands():
    assert parse_views("21.7K") == 21700
    assert parse_views("3.5K") == 3500
    assert parse_views("808") == 808


def test_parse_views_strips_nbsp_like_the_csv_adapter_does():
    # у CRM-адаптері це вже вміє parse_number; асиметрія між ними — випадкова
    assert parse_views("12 345") == 12345


def test_reads_every_post_in_the_channel():
    assert len(parse("trafficdesk").posts) == 14
    assert len(parse("cpa_insider").posts) == 11


def test_key_and_channel_come_from_the_post_address():
    post = by_id(parse("trafficdesk").posts, "trafficdesk/1841")
    assert post.source == "telegram"
    assert post.channel == "trafficdesk"
    assert post.url == "https://t.me/trafficdesk/1841"


def test_time_is_utc():
    post = by_id(parse("trafficdesk").posts, "trafficdesk/1841")
    assert post.published_at == datetime(2026, 7, 2, 8, 5, tzinfo=timezone.utc)
    assert post.source_timezone == "UTC"


def test_missing_views_are_none_not_zero():
    post = by_id(parse("trafficdesk").posts, "trafficdesk/1848")
    assert post.metric_value is None


def test_post_without_text_is_still_a_post():
    posts = parse("trafficdesk").posts
    textless = [p for p in posts if p.text is None]
    assert len(textless) == 1
    assert textless[0].metric_value is not None


def test_forward_is_marked():
    posts = parse("cpa_insider").posts
    assert by_id(posts, "cpa_insider/614").is_forward is True
    assert by_id(posts, "cpa_insider/610").is_forward is False


def test_links_inside_text_are_flattened():
    post = by_id(parse("trafficdesk").posts, "trafficdesk/1843")
    assert "<a" not in post.text
    assert "Деталі в звіті" in post.text


def test_adapter_handles_only_html():
    adapter = TelegramAdapter()
    assert adapter.can_handle(Path("fixtures/telegram/trafficdesk.html")) is True
    assert adapter.can_handle(Path("fixtures/export.csv")) is False
