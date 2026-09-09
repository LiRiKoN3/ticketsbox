from pulse.analytics import above_median, medians_by_source, ratio_to_median


class FakePost:
    def __init__(self, source, metric_value):
        self.source = source
        self.metric_value = metric_value


def test_median_of_odd_count():
    posts = [FakePost("telegram", v) for v in (1000, 3000, 2000)]
    assert medians_by_source(posts) == {"telegram": 2000}


def test_median_of_even_count_is_the_average_of_the_middle_two():
    posts = [FakePost("telegram", v) for v in (1000, 2000, 3000, 5000)]
    assert medians_by_source(posts) == {"telegram": 2500}


def test_posts_without_metric_do_not_take_part():
    posts = [FakePost("telegram", 1000), FakePost("telegram", None), FakePost("telegram", 3000)]
    assert medians_by_source(posts) == {"telegram": 2000}


def test_source_without_any_metric_has_no_median():
    posts = [FakePost("rss", None) for _ in range(16)]
    assert medians_by_source(posts) == {"rss": None}


def test_sources_are_counted_separately():
    posts = [FakePost("telegram", 10_000), FakePost("telegram", 20_000),
             FakePost("crm_csv", 1000), FakePost("crm_csv", 3000)]
    assert medians_by_source(posts) == {"telegram": 15000, "crm_csv": 2000}


def test_ratio_is_none_when_anything_is_missing():
    assert ratio_to_median(None, 2000) is None
    assert ratio_to_median(3000, None) is None
    assert ratio_to_median(3000, 0) is None


def test_ratio_and_flag():
    assert ratio_to_median(3000, 2000) == 1.5
    assert above_median(1.5) is True
    assert above_median(1.0) is False
    assert above_median(None) is None


def test_flag_is_not_decided_by_the_rounded_ratio():
    """Округлення до трьох знаків з'їдало прапорець в околі медіани.

    Це єдина аналітична величина всього завдання, тож помилка тут коштує
    найдорожче: два пости по різні боки медіани діставали однакову відповідь.
    """
    assert above_median(ratio_to_median(4544, 4543.5)) is True
    assert above_median(ratio_to_median(4543, 4543.5)) is False
    assert above_median(ratio_to_median(14101, 14100)) is True
    assert above_median(ratio_to_median(14100, 14100)) is False


def test_ratio_is_none_when_the_median_makes_no_sense():
    """Від'ємна медіана давала перевернуту відповідь: найгірший пост
    отримував above_median=True, а нуль давав vs_median=-0.0."""
    assert ratio_to_median(0, -250.0) is None
    assert ratio_to_median(-500, -250.0) is None
    assert above_median(ratio_to_median(-500, -250.0)) is None
