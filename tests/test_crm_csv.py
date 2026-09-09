from datetime import datetime, timezone
from pathlib import Path

from pulse.sources.crm_csv import CrmCsvAdapter, parse_kyiv_datetime, parse_number

FIXTURE = Path("fixtures/export.csv")
NEWLINE = chr(10)


def parsed():
    return CrmCsvAdapter().parse(FIXTURE)


def by_id(posts, external_id):
    return [p for p in posts if p.external_id == external_id]


def test_parse_number_strips_spaces_including_nbsp():
    assert parse_number("2 436") == 2436
    assert parse_number("8 104") == 8104
    assert parse_number("769") == 769


def test_parse_number_reads_a_thousands_separator():
    # "1,234" — це наявні дані. Видавати їх за None означає збрехати легендою,
    # бо null у контракті значить "даних немає".
    assert parse_number("1,234") == 1234
    assert parse_number("12,345,678") == 12345678


def test_parse_number_refuses_what_it_cannot_read():
    assert parse_number("²") is None      # isdigit() вважав це числом, а int() падав
    assert parse_number("12K") is None
    assert parse_number("1,5") is None      # не тисячі; краще None, ніж вигадане число


def test_parse_number_keeps_the_sign():
    assert parse_number("-42") == -42


def test_parse_number_treats_missing_as_none_not_zero():
    assert parse_number("") is None
    assert parse_number("n/a") is None
    assert parse_number("   ") is None


def test_parse_kyiv_datetime_supports_both_formats():
    # липень: Київ = UTC+3
    assert parse_kyiv_datetime("02.07.2026 12:40") == datetime(2026, 7, 2, 9, 40, tzinfo=timezone.utc)
    assert parse_kyiv_datetime("2026-07-11 14:05") == datetime(2026, 7, 11, 11, 5, tzinfo=timezone.utc)


def test_parse_kyiv_datetime_uses_the_zone_not_a_fixed_offset():
    # січень: Київ = UTC+2. Зашитий "+3" зламався б саме тут.
    assert parse_kyiv_datetime("15.01.2026 12:00") == datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)


def test_reads_all_usable_rows():
    result = parsed()
    assert len(result.posts) == 19        # разом із обома рядками CRM-04102
    assert len(result.rejected) == 1      # порожній рядок


def test_short_row_is_kept_because_it_has_everything_needed():
    post = by_id(parsed().posts, "CRM-04107")[0]
    assert post.metric_value == 7294
    assert post.text.startswith("Зібрали фідбек")
    assert post.url is None


def test_empty_row_is_rejected_with_a_reason():
    rejected = parsed().rejected[0]
    assert rejected.line_number == 12
    assert "порожн" in rejected.reason.lower()


def test_channel_case_is_normalised():
    posts = parsed().posts
    channels = {p.channel for p in posts}
    assert "trafficdesk" in channels
    assert "TrafficDesk" not in channels


def test_missing_and_na_metrics_are_none():
    posts = parsed().posts
    assert by_id(posts, "CRM-04104")[0].metric_value is None
    assert by_id(posts, "CRM-04114")[0].metric_value is None


def test_duplicate_id_appears_twice_in_parse_output():
    # адаптер не дедуплікує — це робота сховища за ключем
    assert len(by_id(parsed().posts, "CRM-04102")) == 2


def test_forward_is_unknown_for_crm():
    assert by_id(parsed().posts, "CRM-04101")[0].is_forward is None


def test_file_without_a_header_keeps_its_first_row(tmp_path):
    """Перший рядок пропускався беззастережно, як заголовок.

    Вивантаження без рядка заголовка втрачало справжній запис: його не було
    ні в posts, ні в rejected_rows, ні в лічильниках.
    """
    path = tmp_path / "noheader.csv"
    path.write_text(NEWLINE.join([
        "CRM-99001;02.07.2026 12:40;TestChan;перший;100;;author",
        "CRM-99002;03.07.2026 12:40;TestChan;другий;200;;author",
    ]), encoding="utf-8")

    result = CrmCsvAdapter().parse(path)
    assert [p.external_id for p in result.posts] == ["CRM-99001", "CRM-99002"]


def test_real_header_is_still_skipped(tmp_path):
    path = tmp_path / "withheader.csv"
    path.write_text(NEWLINE.join([
        "post_id;Дата;Площадка;Текст;reach;Ссылка;Автор",
        "CRM-99001;02.07.2026 12:40;TestChan;перший;100;;author",
    ]), encoding="utf-8")

    result = CrmCsvAdapter().parse(path)
    assert [p.external_id for p in result.posts] == ["CRM-99001"]
