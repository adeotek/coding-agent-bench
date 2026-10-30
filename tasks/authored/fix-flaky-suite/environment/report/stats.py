"""Small statistics helpers behind the report renderer."""
from datetime import datetime, timedelta


def average(values):
    """Arithmetic mean of `values`."""
    return sum(values) / len(values)


def median(values):
    """Median of `values`."""
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        raise ValueError("median of an empty sequence")
    if n % 2:
        return ordered[n // 2]
    return (ordered[n // 2 - 1] + ordered[n // 2]) / 2


def week_start(now=None):
    """The Monday of the week containing `now` (defaults to the current time)."""
    now = now or datetime.now()
    return (now - timedelta(days=now.weekday())).date()


def summarize(counts):
    """Render a {label: count} mapping as one `label: count` line per entry."""
    labels = set(counts)
    return "\n".join(f"{label}: {counts[label]}" for label in labels)
