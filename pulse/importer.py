"""Обхід теки з даними: файл -> адаптер -> сховище."""

from dataclasses import dataclass, field
from pathlib import Path

from pulse.db import forget_rejected, save_posts, save_rejected
from pulse.sources.registry import adapter_for


@dataclass
class ImportSummary:
    imported: int = 0                 # скільки постів прочитано з файлів
    stored: int = 0                   # скільки з них лягло в базу після ключа
    rejected: int = 0                 # скільки рядків відкинуто з причиною
    by_source: dict[str, int] = field(default_factory=dict)
    failed_files: list[str] = field(default_factory=list)


def files_under(root: Path) -> list[Path]:
    """Файли, які варто спробувати прочитати.

    Неіснуючий шлях — це помилка, а не порожній результат: rglob() на друкарській
    помилці мовчки повертав нуль файлів, і імпорт рапортував успіх.
    """
    root = Path(root)
    if not root.exists():
        raise ValueError(f"шлях не існує: {root}")
    if root.is_file():
        return [root]
    return [path for path in sorted(root.rglob("*")) if path.is_file()]


def import_path(root: Path, session) -> ImportSummary:
    summary = ImportSummary()
    # Ключі рахуємо за весь прогін, а не пофайлово: два різні файли можуть
    # дати той самий (source, external_id), і пофайлова сума цього не помітить.
    seen: set[tuple[str, str]] = set()

    for path in files_under(root):
        adapter = adapter_for(path)
        if adapter is None:
            continue

        # Кожен файл фіксується окремо. Інакше збій на останньому файлі
        # відкочує все прочитане до нього — саме так і губився цілий імпорт.
        try:
            result = adapter.parse(path)
            save_posts(session, result.posts)
            # Файл читається наново — старі відомості про його брак застаріли.
            forget_rejected(session, path)
            save_rejected(session, result.rejected)
            session.commit()
        except Exception as error:
            # Адаптери самі відкидають нечитабельні рядки; сюди долітає лише
            # те, чого ми не передбачили, — і воно не має валити решту файлів.
            session.rollback()
            summary.failed_files.append(f"{path}: {type(error).__name__}: {error}")
            continue

        summary.imported += len(result.posts)
        seen.update((p.source, p.external_id) for p in result.posts)
        summary.stored = len(seen)
        summary.rejected += len(result.rejected)
        summary.by_source[adapter.name] = (
            summary.by_source.get(adapter.name, 0) + len(result.posts)
        )

    return summary
