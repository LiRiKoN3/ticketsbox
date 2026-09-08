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
