"""Явний список джерел.

Щоб додати четверте джерело: створити файл поруч і дописати один рядок нижче.
Автопошуку файлів тут навмисно немає — список видно очима.
"""

from pulse.sources.crm_csv import CrmCsvAdapter
from pulse.sources.rss import RssAdapter
from pulse.sources.telegram import TelegramAdapter

ADAPTERS: list = [
    TelegramAdapter(),
    RssAdapter(),
    CrmCsvAdapter(),
]


def adapter_for(path):
    for adapter in ADAPTERS:
        if adapter.can_handle(path):
            return adapter
    return None


def all_adapters() -> list:
    """Усі оголошені джерела. Звіт показує їх усі, навіть якщо за період
    у якогось нуль постів: інакше нуль не відрізнити від "джерела не існує"."""
    return list(ADAPTERS)


def adapter_by_name(name: str):
    """None, якщо джерела в реєстрі немає: дані могли накопичитись до того,
    як джерело перейменували, і звіт по них має лишитися можливим."""
    for adapter in ADAPTERS:
        if adapter.name == name:
            return adapter
    return None
