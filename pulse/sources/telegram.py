"""Адаптер сторінок t.me/s/<channel>."""

from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from pulse.model import CanonicalPost, missing_required
from pulse.sources.base import ParseResult, Rejected


def parse_views(raw: str) -> int | None:
    """"21.7K" -> 21700. Telegram округлює — точного числа не існує."""
    value = raw.strip().upper().replace(" ", "")
    if not value:
        return None
    if value.endswith("K"):
        return int(round(float(value[:-1]) * 1_000))
    if value.endswith("M"):
        return int(round(float(value[:-1]) * 1_000_000))
    return int(value)


class TelegramAdapter:
    name = "telegram"
    metric_name = "views"
    metric_precision = "rounded"   # 21.7K — це 21650...21749

    def can_handle(self, path: Path) -> bool:
        return path.suffix == ".html"

    def parse(self, path: Path) -> ParseResult:
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        result = ParseResult()

        for number, node in enumerate(soup.select(".tgme_widget_message"), start=1):
            external_id = (node.get("data-post") or "").strip()
            time_node = node.select_one("time[datetime]")
            published_at = None
            if time_node:
                published_at = datetime.fromisoformat(
                    time_node["datetime"]
                ).astimezone(timezone.utc)

            values = {
                "external_id": external_id,
                "channel": external_id.split("/")[0] if "/" in external_id else "",
                "published_at": published_at,
            }
            absent = missing_required(values)
            if absent:
                result.rejected.append(
                    Rejected(
                        source_file=str(path),
                        line_number=number,
                        reason=f"бракує обов'язкових полів: {', '.join(absent)}",
                        raw=str(node)[:1000],
                    )
                )
                continue

            text_node = node.select_one(".tgme_widget_message_text")
            text = text_node.get_text("\n").strip() if text_node else ""

            views_node = node.select_one(".tgme_widget_message_views")

            result.posts.append(
                CanonicalPost(
                    source=self.name,
                    external_id=external_id,
                    channel=values["channel"],
                    published_at=published_at,
                    source_timezone="UTC",   # у datetime уже стоїть +00:00
                    text=text or None,       # пост лише з картинкою — це не порожній рядок
                    metric_value=parse_views(views_node.get_text()) if views_node else None,
                    url=f"https://t.me/{external_id}",
                    is_forward=bool(node.select_one(".tgme_widget_message_forwarded_from")),
                )
            )

        return result
