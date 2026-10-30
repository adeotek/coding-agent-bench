from datetime import datetime

import stats


def test_average_simple():
    assert stats.average([1, 2, 3]) == 2


def test_average_decimals():
    assert stats.average([0.1, 0.2, 0.3]) == 0.2


def test_median_odd():
    assert stats.median([3, 1, 2]) == 2


def test_median_even():
    assert stats.median([1, 2, 3, 4]) == 2.5


def test_median_rejects_empty():
    try:
        stats.median([])
    except ValueError:
        return
    raise AssertionError("median of an empty sequence should raise ValueError")


def test_summarize_is_stable():
    counts = {"beta": 2, "alpha": 1, "gamma": 3}
    assert stats.summarize(counts) == "alpha: 1\nbeta: 2\ngamma: 3"


def test_week_start_is_monday():
    assert stats.week_start(datetime(2026, 2, 4, 12, 0)).weekday() == 0
    assert stats.week_start(datetime(2026, 2, 4, 12, 0)).isoformat() == "2026-02-02"