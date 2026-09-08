"""Адаптер RSS 2.0. Метрики тут немає в принципі."""

import xml.etree.ElementTree as ElementTree
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from bs4 import BeautifulSoup

from pulse.model import CanonicalPost, missing_required
from pulse.sources.base import ParseResult, Rejected


def strip_html(raw: str) -> str:
    """Опис у стрічці буває з HTML усередині CDATA."""
    return BeautifulSoup(raw or "", "html.parser").get_text(" ").strip()


def format_offset(value: datetime) -> str:
    """Зона оригіналу у вигляді, який видно очима: UTC або +03:00."""
    offset = value.utcoffset() or timedelta(0)
    if offset == timedelta(0):
        return "UTC"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return f"{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _text_of(node, tag: str) -> str:
    found = node.find(tag)
    return (found.text or "").strip() if found is not None else ""


class RssAdapter:
    name = "rss"
    metric_name = None        # джерело метрики не надає
    metric_precision = None

    def can_handle(self, path: Path) -> bool:
        return path.suffix == ".xml"

    def parse(self, path: Path) -> ParseResult:
        root = ElementTree.parse(path).getroot()
        channel_node = root.find("channel")
        channel = _text_of(channel_node, "title")
        result = ParseResult()

        for number, item in enumerate(channel_node.findall("item"), start=1):
            raw_date = _text_of(item, "pubDate")
            published_at = original = None
            if raw_date:
                original = parsedate_to_datetime(raw_date)
                published_at = original.astimezone(timezone.utc)

            values = {
                "external_id": _text_of(item, "guid"),
                "channel": channel,
                "published_at": published_at,
            }
            absent = missing_required(values)
            if absent:
                result.rejected.append(
                    Rejected(
                        source_file=str(path),
                        line_number=number,
                        reason=f"бракує обов'язкових полів: {', '.join(absent)}",
                        raw=ElementTree.tostring(item, encoding="unicode")[:1000],
                    )
                )
                continue

            title = _text_of(item, "title")
            body = strip_html(_text_of(item, "description"))
            text = "\n\n".join(part for part in (title, body) if part)

            result.posts.append(
                CanonicalPost(
                    source=self.name,
                    external_id=values["external_id"],
                    channel=channel,
                    published_at=published_at,
                    source_timezone=format_offset(original),
                    text=text or None,
                    metric_value=None,     # метрики немає, і це не нуль
                    url=_text_of(item, "link") or None,
                    is_forward=None,       # у стрічці такого поняття немає
                )
            )

        return result
