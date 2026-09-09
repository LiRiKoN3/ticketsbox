"""Одна аналітична величина: відношення метрики поста до медіани його джерела.

Правило єдине для всіх джерел. Джерело без метрики (RSS) отримує None
не через окрему гілку в коді, а тому що в нього немає чого рахувати.
"""

from statistics import median


def medians_by_source(posts) -> dict[str, float | None]:
    values: dict[str, list[int]] = {}
    for post in posts:
        values.setdefault(post.source, [])
        if post.metric_value is not None:
            values[post.source].append(post.metric_value)

    return {
        source: (median(numbers) if numbers else None)
        for source, numbers in values.items()
    }


def ratio_to_median(value: int | None, median_value: float | None) -> float | None:
    """None означає "порахувати неможливо", а не "нуль".

    Повертається точне відношення. Округлення — справа того, хто складає
    контракт: якщо округлити тут, прапорець above_median почне рахуватися
    з округленого числа і в околі медіани відповідатиме неправильно.
    """
    # median_value <= 0 буває, коли джерело віддало від'ємні числа: відношення
    # до такої медіани перевертає відповідь, тож чесніше сказати "не рахується".
    if value is None or median_value is None or median_value <= 0:
        return None
    return value / median_value


def above_median(ratio: float | None) -> bool | None:
    return None if ratio is None else ratio > 1
