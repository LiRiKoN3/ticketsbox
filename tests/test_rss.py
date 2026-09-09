from datetime import datetime, timezone
from pathlib import Path

from pulse.sources.rss import RssAdapter, strip_html

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "rss"


def parse(name):
    return RssAdapter().parse(FIXTURES / f"{name}.xml")


def by_id(posts, external_id):
    return next(p for p in posts if p.external_id == external_id)


def test_strip_html_returns_plain_text():
    raw = "<p>Чек-лист із семи пунктів.</p><p>Читати на <a href='#'>сайті</a>.</p>"
    text = strip_html(raw)
    assert "<p>" not in text
    assert "Чек-лист із семи пунктів." in text
    assert "сайті" in text


def test_reads_every_item():
    assert len(parse("affnews").posts) == 9
    assert len(parse("adtech-digest").posts) == 7


def test_guid_is_the_key_and_feed_title_is_the_channel():
    post = by_id(parse("affnews").posts, "affnews.example/affnews-3002")
    assert post.source == "rss"
    assert post.channel == "AffNews"
    assert post.url == "https://affnews.example/post/affnews-3002"


def test_rfc822_with_offset_converts_to_utc():
    post = by_id(parse("affnews").posts, "affnews.example/affnews-3000")
    assert post.published_at == datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    assert post.source_timezone == "+03:00"


def test_utc_feed_keeps_utc():
    post = by_id(parse("adtech-digest").posts, "adtech.example/adtech-digest-3000")
    assert post.published_at == datetime(2026, 7, 2, 18, 0, tzinfo=timezone.utc)
    assert post.source_timezone == "UTC"


def test_text_is_title_plus_cleaned_description():
    post = by_id(parse("affnews").posts, "affnews.example/affnews-3002")
    assert post.text.startswith("Як не втратити домен на модерації")
    assert "<p>" not in post.text
    assert "Чек-лист" in post.text


def test_rss_never_has_a_metric():
    for post in parse("affnews").posts + parse("adtech-digest").posts:
        assert post.metric_value is None


def test_forward_is_unknown_for_rss():
    assert by_id(parse("affnews").posts, "affnews.example/affnews-3000").is_forward is None


def test_repeated_content_with_new_guid_is_a_separate_post():
    posts = parse("affnews").posts
    first = by_id(posts, "affnews.example/affnews-3000")
    later = by_id(posts, "affnews.example/affnews-3008")
    assert first.text == later.text
    assert first.external_id != later.external_id
