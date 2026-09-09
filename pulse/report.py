"""Готовий до аналізу зріз. Це контракт, а не дамп таблиці."""

from datetime import datetime, timedelta, timezone

from pulse.analytics import above_median, medians_by_source, ratio_to_median
from pulse.db import all_posts, count_rejected
from pulse.sources.registry import adapter_by_name, all_adapters

LEGEND = {
    "null": "даних немає; ніколи не означає нуль",
    "metric": "значення метрики свого джерела; яка це величина — див. sources",
    "vs_median": "відношення метрики до медіани свого джерела за цей період, округлене до 6 знаків",
    "above_median": "метрика вище за медіану; рахується з точного відношення, не з округленого vs_median",
    "is_forward": "true — репост чужого каналу; null — джерело такого поняття не має",
    "source_timezone": "зона, з якої published_at перераховано в UTC",
}


def build_report(session, days: int, until) -> dict:
    since = until - timedelta(days=days)
    posts = [p for p in all_posts(session) if since <= p.published_at <= until]
    medians = medians_by_source(posts)

    # Усі оголошені джерела плюс ті, що трапились у даних, але з реєстру зникли.
    # Джерело з нулем постів за період лишається в списку з нулями і null —
    # так модель бачить різницю між "нічого не було" і "джерела не існує".
    known = {a.name for a in all_adapters()}
    sources = []
    for name in sorted(known | {p.source for p in posts}):
        adapter = adapter_by_name(name)
        of_source = [p for p in posts if p.source == name]
        sources.append(
            {
                "source": name,
                "metric": adapter.metric_name if adapter else None,
                "metric_precision": adapter.metric_precision if adapter else None,
                "posts": len(of_source),
                "with_metric": sum(1 for p in of_source if p.metric_value is not None),
                "median": medians.get(name),
            }
        )

    rows = []
    for post in sorted(posts, key=lambda p: (p.published_at, p.external_id)):
        ratio = ratio_to_median(post.metric_value, medians.get(post.source))
        rows.append(
            {
                "source": post.source,
                "channel": post.channel,
                "id": post.external_id,
                "published_at": post.published_at.isoformat(),
                "source_timezone": post.source_timezone,
                "text": post.text,
                "metric": post.metric_value,
                "vs_median": None if ratio is None else round(ratio, 6),
                "above_median": above_median(ratio),
                "is_forward": post.is_forward,
            }
        )

    return {
        "slice": {
            "from": since.isoformat(),
            "to": until.isoformat(),
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "posts_total": len(posts),
            "rejected_on_import": count_rejected(session),
        },
        "sources": sources,
        "posts": rows,
        "legend": LEGEND,
    }
