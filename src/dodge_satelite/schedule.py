"""Interval algebra and maximum-count equal-duration exposure scheduling."""

from .models import Interval


def merge(intervals: list[Interval], duration: float) -> list[Interval]:
    result = []
    for item in sorted(intervals):
        start, end = max(0.0, item.start_s), min(duration, item.end_s)
        if end <= start:
            continue
        if result and start <= result[-1].end_s:
            result[-1] = Interval(result[-1].start_s, max(end, result[-1].end_s))
        else:
            result.append(Interval(start, end))
    return result


def available(blocked: list[Interval], duration: float) -> list[Interval]:
    result, cursor = [], 0.0
    for item in merge(blocked, duration):
        if item.start_s > cursor:
            result.append(Interval(cursor, item.start_s))
        cursor = item.end_s
    if cursor < duration:
        result.append(Interval(cursor, duration))
    return result


def schedule(blocked: list[Interval], duration: float, exposure: float, readout: float):
    if exposure <= 0 or readout < 0:
        raise ValueError("Exposure must be positive and readout non-negative.")
    result, ready = [], 0.0
    for window in available(blocked, duration):
        cursor = max(window.start_s, ready)
        while cursor + exposure <= window.end_s + 1e-9:
            end = min(cursor + exposure, window.end_s)
            result.append(Interval(cursor, end))
            ready = end + readout
            cursor = ready
    return result


def overlaps(a: Interval, b: Interval):
    return a.start_s < b.end_s and b.start_s < a.end_s
