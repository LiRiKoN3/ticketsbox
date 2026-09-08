from datetime import datetime, timezone

from pulse.model import CanonicalPost, missing_required


def test_missing_required_lists_absent_fields():
    assert missing_required({"external_id": "", "channel": "x", "published_at": None}) == [
        "external_id",
        "published_at",
    ]


def test_missing_required_empty_when_all_present():
    values = {"external_id": "trafficdesk/1841", "channel": "trafficdesk",
              "published_at": datetime(2026, 7, 2, 8, 5, tzinfo=timezone.utc)}
    assert missing_required(values) == []


def test_optional_fields_default_to_none():
    post = CanonicalPost(
        source="telegram",
        external_id="trafficdesk/1841",
        channel="trafficdesk",
        published_at=datetime(2026, 7, 2, 8, 5, tzinfo=timezone.utc),
        source_timezone="UTC",
    )
    assert post.text is None
    assert post.metric_value is None
    assert post.url is None
    assert post.is_forward is None
