"""Адаптер RSS 2.0. Метрики тут немає в принципі."""

import xml.etree.ElementTree as ElementTree
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from pulse.model import CanonicalPost, missing_required
from pulse.sources.base import (WHOLE_FILE, ParseResult, Rejected, Unreadable,
                                format_offset, reason_of)


def strip_html(raw: str) -> str:
    """Опис у стрічці буває з HTML усередині CDATA."""
    return BeautifulSoup(raw or "", "html.parser").get_text(" ").strip()


def feed_key(channel_node) -> str:
    """Ім'я стрічки, у межах якої guid обіцяє бути унікальним.

    RSS вимагає унікальності guid лише всередині однієї стрічки, тож дослівний
    guid ключем бути не може: дві стрічки з <guid>1</guid> затерли б одна одну.
    Беремо хост із <channel><link> — він стабільніший за назву стрічки.
    """
    link = _text_of(channel_node, "link")
    host = urlparse(link).netloc if link else ""
    return host or _text_of(channel_node, "title")


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
        result = ParseResult()

        # Побитий XML — це відмова файлу цілком, а не привід валити весь імпорт.
        try:
            root = ElementTree.parse(path).getroot()
        except (ElementTree.ParseError, OSError, UnicodeDecodeError) as error:
            result.rejected.append(
                Rejected(str(path), WHOLE_FILE, reason_of(error), "")
            )
            return result

        channel_node = root.find("channel")
        if channel_node is None:
            result.rejected.append(
                Rejected(str(path), WHOLE_FILE, "у стрічці немає <channel>", "")
            )
            return result

        channel = _text_of(channel_node, "title")
        prefix = feed_key(channel_node)

        for number, item in enumerate(channel_node.findall("item"), start=1):
            try:
                result.posts.append(self._read_item(item, channel, prefix))
            except Exception as error:
                result.rejected.append(
                    Rejected(
                        source_file=str(path),
                        line_number=number,
                        reason=reason_of(error),
                        raw=ElementTree.tostring(item, encoding="unicode")[:1000],
                    )
                )

        return result

    def _read_item(self, item, channel: str, prefix: str) -> CanonicalPost:
        raw_date = _text_of(item, "pubDate")
        published_at = original = None
        if raw_date:
            # Дата присутня, але нерозбірна — це відмова рядка, не всього файлу.
            original = parsedate_to_datetime(raw_date)
            if original.tzinfo is None:
                # RFC 822 дозволяє -0000: "час відомий, зона — ні". Вважаємо його
                # UTC явно, інакше astimezone() підставить зону цієї машини і
                # published_at залежатиме від того, де запустили програму.
                published_at = original.replace(tzinfo=timezone.utc)
            else:
                published_at = original.astimezone(timezone.utc)

        guid = _text_of(item, "guid")
        values = {
            # Ключ унікальний у межах джерела — це обов'язок адаптера, не сховища.
            "external_id": f"{prefix}/{guid}" if prefix and guid else guid,
            "channel": channel,
            "published_at": published_at,
        }
        absent = missing_required(values)
        if absent:
            raise Unreadable(f"бракує обов'язкових полів: {', '.join(absent)}")

        title = _text_of(item, "title")
        body = strip_html(_text_of(item, "description"))
        text = "\n\n".join(part for part in (title, body) if part)

        return CanonicalPost(
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
