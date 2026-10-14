import random
from dataclasses import replace
from datetime import timedelta
from functools import lru_cache

import pytest

from dodge_satelite.models import Equipment, Interval, PlanConfig, Site, Target, utc
from dodge_satelite.schedule import available, merge, overlaps, schedule


def test_timezone_conversion():
    assert utc("2026-10-14T22:00:00+09:00") == utc("2026-10-14T13:00:00Z")
    with pytest.raises(ValueError, match="offset"):
        utc("2026-10-14T22:00:00")


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Site(latitude_deg=91),
        lambda: Site(longitude_deg=float("nan")),
        lambda: Equipment(focal_length_mm=0),
        lambda: Equipment(focal_length_mm=1),
        lambda: Target(360, 0),
        lambda: Target(0, -91),
        lambda: Target(True, 0),
    ],
)
def test_invalid_parameters(factory):
    with pytest.raises(ValueError):
        factory()


@pytest.mark.parametrize(
    "key,value", [("sample_s", 0), ("exposure_s", -1), ("padding_s", -1), ("sunlit_only", "false")]
)
def test_invalid_config(inputs, key, value):
    with pytest.raises(ValueError):
        replace(inputs[0], **{key: value})


def test_duration_and_workload(inputs):
    config, _ = inputs
    with pytest.raises(ValueError):
        replace(config, end=config.start)
    with pytest.raises(ValueError, match="samples"):
        replace(config, end=config.start + timedelta(hours=24), sample_s=0.05)


def test_profile_roundtrip(inputs, tmp_path):
    config, _ = inputs
    path = tmp_path / "設定.json"
    config.save(path)
    assert PlanConfig.load(path) == config
    assert config.equipment.radius_deg > config.equipment.width_deg / 2


def test_interval_clipping_merge_and_boundary():
    blocked = [Interval(-5, 2), Interval(1, 4), Interval(4, 5), Interval(9, 15)]
    assert merge(blocked, 10) == [Interval(0, 5), Interval(9, 10)]
    assert available(blocked, 10) == [Interval(5, 9)]
    assert schedule(blocked, 10, 2, 0) == [Interval(5, 7), Interval(7, 9)]
    assert not overlaps(Interval(0, 2), Interval(2, 3))


def test_readout_crosses_blocked_gap():
    assert schedule([Interval(2, 3)], 10, 2, 4) == [Interval(0, 2), Interval(6, 8)]


def test_greedy_matches_exhaustive_small_integer_schedules():
    rng = random.Random(42)
    for _ in range(100):
        duration = 20
        exposure, readout = rng.randint(1, 5), rng.randint(0, 3)
        blocked = [
            Interval(start, start + rng.randint(1, 4))
            for start in rng.sample(range(duration - 4), 4)
        ]

        @lru_cache(None)
        def best(t):
            if t + exposure > duration:
                return 0
            skip = best(t + 1)
            if any(overlaps(Interval(t, t + exposure), item) for item in blocked):
                return skip
            return max(skip, 1 + best(t + exposure + readout))

        result = schedule(blocked, duration, exposure, readout)
        assert len(result) == best(0)
        assert all(not overlaps(e, b) for e in result for b in blocked)
