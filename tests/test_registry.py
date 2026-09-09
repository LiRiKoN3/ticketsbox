from pathlib import Path

from pulse.sources.base import ParseResult, Rejected
from pulse.sources.registry import ADAPTERS, adapter_by_name, adapter_for


class FakeAdapter:
    name = "fake"
    metric_name = "clicks"
    metric_precision = "exact"

    def can_handle(self, path: Path) -> bool:
        return path.suffix == ".fake"

    def parse(self, path: Path) -> ParseResult:
        return ParseResult()


def test_parse_result_starts_empty():
    result = ParseResult()
    assert result.posts == []
    assert result.rejected == []


def test_rejected_holds_enough_to_find_the_row():
    row = Rejected(source_file="fixtures/export.csv", line_number=12,
                   reason="порожній рядок", raw="")
    assert row.line_number == 12
    assert row.reason == "порожній рядок"


def test_adapter_for_picks_by_file(monkeypatch):
    monkeypatch.setattr("pulse.sources.registry.ADAPTERS", [FakeAdapter()])
    assert adapter_for(Path("data/x.fake")).name == "fake"
    assert adapter_for(Path("data/x.txt")) is None


def test_adapter_by_name_finds_registered_adapter(monkeypatch):
    monkeypatch.setattr("pulse.sources.registry.ADAPTERS", [FakeAdapter()])
    assert adapter_by_name("fake").metric_name == "clicks"


def test_registry_is_an_explicit_list():
    assert isinstance(ADAPTERS, list)


def test_uppercase_extensions_are_recognised():
    """Windows не розрізняє регістр у назвах, деякі CRM віддають EXPORT.CSV.

    Формат підтримуваний — файл просто не впізнавався і зникав без сигналу.
    """
    assert adapter_for(Path("data/EXPORT.CSV")).name == "crm_csv"
    assert adapter_for(Path("data/CHAN.HTML")).name == "telegram"
    assert adapter_for(Path("data/FEED.XML")).name == "rss"
