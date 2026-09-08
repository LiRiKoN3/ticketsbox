"""Готовий до аналізу зріз. Це контракт, а не дамп таблиці."""

from datetime import datetime, timedelta, timezone

from pulse.analytics import above_median, medians_by_source, ratio_to_median
from pulse.db import all_posts, count_rejected
from pulse.sources.registry import adapter_by_name

LEGEND = {
    "null": "даних немає; ніколи не означає нуль",
    "metric": "значення метрики свого джерела; яка це величина — див. sources",
    "vs_median": "відношення метрики до медіани свого джерела за цей період",
    "above_median": "vs_median > 1",
    "is_forward": "true — репост чужого каналу; null — джерело такого поняття не має",
    "source_timezone": "зона, з якої published_at перераховано в UTC",
}


def build_report(session, days: int, until) -> dict:
    since = until - timedelta(days=days)
    posts = [p for p in all_posts(session) if since <= p.published_at <= until]
    medians = medians_by_source(posts)

    sources = []
    for name in sorted({p.source for p in posts}):
        adapter = adapter_by_name(name)
        of_source = [p for p in posts if p.source == name]
        sources.append(
            {
                "source": name,
                "metric": adapter.metric_name,
                "metric_precision": adapter.metric_precision,
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
                "vs_median": ratio,
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
