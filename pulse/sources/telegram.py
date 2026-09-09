"""Адаптер сторінок t.me/s/<channel>."""

from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from pulse.model import CanonicalPost, missing_required
from pulse.sources.base import (WHOLE_FILE, ParseResult, Rejected, Unreadable,
                                format_offset, reason_of)


def parse_views(raw: str) -> int | None:
    """"21.7K" -> 21700. Telegram округлює — точного числа не існує."""
    value = raw.strip().upper().replace(" ", "")
    if not value:
        return None
    # Нерозбірне значення дає None, а не виняток: перегляди не входять до
    # обов'язкових полів, тож через них не варто втрачати сам пост.
    try:
        if value.endswith("K"):
            return int(round(float(value[:-1]) * 1_000))
        if value.endswith("M"):
            return int(round(float(value[:-1]) * 1_000_000))
        return int(value)
    except ValueError:
        return None


class TelegramAdapter:
    name = "telegram"
    metric_name = "views"
    metric_precision = "rounded"   # 21.7K — це 21650...21749

    def can_handle(self, path: Path) -> bool:
        return path.suffix == ".html"

    def parse(self, path: Path) -> ParseResult:
        result = ParseResult()

        try:
            soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        except (OSError, UnicodeDecodeError) as error:
            result.rejected.append(Rejected(str(path), WHOLE_FILE, reason_of(error), ""))
            return result

        for number, node in enumerate(soup.select(".tgme_widget_message"), start=1):
            try:
                result.posts.append(self._read_post(node))
            except Exception as error:
                result.rejected.append(
                    Rejected(
                        source_file=str(path),
                        line_number=number,
                        reason=reason_of(error),
                        raw=str(node)[:1000],
                    )
                )

        return result

    def _read_post(self, node) -> CanonicalPost:
        external_id = (node.get("data-post") or "").strip()
        time_node = node.select_one("time[datetime]")
        published_at = original = None
        if time_node:
            # Атрибут є, але нерозбірний — відмовляє цей пост, а не вся сторінка.
            original = datetime.fromisoformat(time_node["datetime"])
            published_at = (
                original.replace(tzinfo=timezone.utc)
                if original.tzinfo is None
                else original.astimezone(timezone.utc)
            )

        values = {
            "external_id": external_id,
            "channel": external_id.split("/")[0] if "/" in external_id else "",
            "published_at": published_at,
        }
        absent = missing_required(values)
        if absent:
            raise Unreadable(f"бракує обов'язкових полів: {', '.join(absent)}")

        text_node = node.select_one(".tgme_widget_message_text")
        text = text_node.get_text("\n").strip() if text_node else ""

        views_node = node.select_one(".tgme_widget_message_views")

        return CanonicalPost(
            source=self.name,
            external_id=external_id,
            channel=values["channel"],
            published_at=published_at,
            source_timezone=format_offset(original),
            text=text or None,       # пост лише з картинкою — це не порожній рядок
            metric_value=parse_views(views_node.get_text()) if views_node else None,
            url=f"https://t.me/{external_id}",
            is_forward=bool(node.select_one(".tgme_widget_message_forwarded_from")),
        )
