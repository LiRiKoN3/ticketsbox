"""Явний список джерел.

Щоб додати четверте джерело: створити файл поруч і дописати один рядок нижче.
Автопошуку файлів тут навмисно немає — список видно очима.
"""

from pulse.sources.rss import RssAdapter
from pulse.sources.telegram import TelegramAdapter

ADAPTERS: list = [
    TelegramAdapter(),
    RssAdapter(),
]


def adapter_for(path):
    for adapter in ADAPTERS:
        if adapter.can_handle(path):
            return adapter
    return None


def adapter_by_name(name: str):
    for adapter in ADAPTERS:
        if adapter.name == name:
            return adapter
    raise KeyError(f"невідоме джерело: {name}")
