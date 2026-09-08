"""Обхід теки з даними: файл -> адаптер -> сховище."""

from dataclasses import dataclass, field
from pathlib import Path

from pulse.db import save_posts, save_rejected
from pulse.sources.registry import adapter_for


@dataclass
class ImportSummary:
    imported: int = 0
    rejected: int = 0
    by_source: dict[str, int] = field(default_factory=dict)


def import_path(root: Path, session) -> ImportSummary:
    summary = ImportSummary()

    for path in sorted(Path(root).rglob("*")):
        if not path.is_file():
            continue
        adapter = adapter_for(path)
        if adapter is None:
            continue

        result = adapter.parse(path)
        save_posts(session, result.posts)
        save_rejected(session, result.rejected)

        summary.imported += len(result.posts)
        summary.rejected += len(result.rejected)
        summary.by_source[adapter.name] = (
            summary.by_source.get(adapter.name, 0) + len(result.posts)
        )

    return summary
