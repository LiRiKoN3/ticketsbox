"""Сховище. Знає канонічну форму і нічого не знає про формати джерел."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (Boolean, DateTime, Integer, String, Text, TypeDecorator,
                        UniqueConstraint, create_engine, delete, func, select)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from pulse.model import CanonicalPost


class UtcDateTime(TypeDecorator):
    """Час у програмі — завжди tz-aware UTC. SQLite зони не зберігає,
    тому в базу лягає naive UTC, а тег повертається на читанні.
    Конвертація живе тут, в одному місці, і більше ніде."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    pass


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(200))
    channel: Mapped[str] = mapped_column(String(200))
    published_at: Mapped[datetime] = mapped_column(UtcDateTime)
    source_timezone: Mapped[str] = mapped_column(String(64))
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_forward: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_post_key"),)


class RejectedRow(Base):
    """Рядки, які не вдалося прочитати. Нічого не зникає мовчки."""

    __tablename__ = "rejected_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_file: Mapped[str] = mapped_column(String(500))
    line_number: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(300))
    raw: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("source_file", "line_number", name="uq_rejected_key"),
    )


@contextmanager
def open_session(db_path: str):
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        Base.metadata.create_all(engine)
        # expire_on_commit=False: після коміту прочитані пости лишаються придатними
        # до використання. Інакше будь-яке звертання до них поза блоком with
        # падає з DetachedInstanceError.
        with Session(engine, expire_on_commit=False) as session:
            yield session
            session.commit()
    finally:
        # Без dispose() пул тримає з'єднання відкритим: на Windows файл бази
        # лишається заблокованим, а інтерпретатор сипле ResourceWarning.
        engine.dispose()


def save_posts(session: Session, posts: list[CanonicalPost]) -> int:
    """Записує пости, оновлюючи наявні за ключем (source, external_id)."""
    if not posts:
        return 0

    # Дедуплікація в межах пачки: у CSV той самий post_id трапляється двічі.
    # Виграє останній прочитаний. Робимо це явно, а не покладаємось на те,
    # як конкретна версія SQLite поводиться з дублем ключа в одному INSERT
    # (старі версії відповідають помилкою).
    unique = {(p.source, p.external_id): p for p in posts}

    rows = [
        {
            "source": p.source,
            "external_id": p.external_id,
            "channel": p.channel,
            "published_at": p.published_at,
            "source_timezone": p.source_timezone,
            "text": p.text,
            "metric_value": p.metric_value,
            "url": p.url,
            "is_forward": p.is_forward,
        }
        for p in unique.values()
    ]

    statement = sqlite_insert(Post).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["source", "external_id"],
        set_={
            "channel": statement.excluded.channel,
            "published_at": statement.excluded.published_at,
            "source_timezone": statement.excluded.source_timezone,
            "text": statement.excluded.text,
            "metric_value": statement.excluded.metric_value,
            "url": statement.excluded.url,
            "is_forward": statement.excluded.is_forward,
        },
    )
    session.execute(statement)
    session.flush()
    return len(rows)


def normalized_path(value) -> str:
    """Один файл — один ключ, як би не набрали шлях у командному рядку.
    Без цього "fixtures/" і "C:/.../fixtures" дають два рядки про той самий рядок."""
    return str(Path(value).resolve())


def forget_rejected(session: Session, source_file) -> int:
    """Забути все, що знали про відкинуті рядки цього файлу.

    Викликається перед повторним читанням файлу: інакше число відкинутих
    лише росте й лишається завищеним навіть після того, як джерело виправили.
    """
    result = session.execute(
        delete(RejectedRow).where(
            RejectedRow.source_file == normalized_path(source_file)
        )
    )
    return result.rowcount or 0


REASON_LIMIT = 300                # стільки вміщує колонка reason


def _upsert_rejected(session: Session, rows: list[dict]) -> int:
    statement = sqlite_insert(RejectedRow).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["source_file", "line_number"],
        set_={"reason": statement.excluded.reason, "raw": statement.excluded.raw},
    )
    session.execute(statement)
    session.flush()
    return len(rows)


def save_rejected(session: Session, rejected) -> int:
    if not rejected:
        return 0

    return _upsert_rejected(session, [
        {
            "source_file": normalized_path(r.source_file),
            "line_number": r.line_number,
            "reason": r.reason[:REASON_LIMIT],
            "raw": r.raw,
        }
        for r in rejected
    ])


def save_failed_file(session: Session, source_file, reason: str) -> int:
    """Файл, який не вдалося опрацювати цілком.

    Лягає в ту саму таблицю з line_number = 0, щоб неповнота зрізу дійшла до
    звіту, а не лишилась однією фразою в консолі: модель консолі не бачить.
    """
    return _upsert_rejected(session, [{
        "source_file": normalized_path(source_file),
        "line_number": 0,
        "reason": reason[:REASON_LIMIT],
        "raw": "",
    }])


def all_posts(session: Session) -> list[Post]:
    return list(session.scalars(select(Post)))


def count_rejected(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(RejectedRow)) or 0


def newest_published_at(session: Session) -> datetime | None:
    """Найсвіжіша дата в базі. Через order_by, а не func.max — так спрацьовує
    зворотне перетворення UtcDateTime і повертається tz-aware значення."""
    return session.scalar(
        select(Post.published_at).order_by(Post.published_at.desc()).limit(1)
    )
