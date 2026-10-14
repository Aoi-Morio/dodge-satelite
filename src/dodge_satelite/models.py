"""Validated, portable observation profiles. All internal datetimes are UTC."""

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path


def utc(value: str | datetime) -> datetime:
    if not isinstance(value, (str, datetime)):
        raise ValueError("Time must be an ISO 8601 string or a timezone-aware datetime.")
    value = (
        datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    )
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Time must include Z or a UTC offset, for example +09:00.")
    return value.astimezone(UTC)


def iso(value: datetime) -> str:
    return utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def bounded(name: str, value: float, low: float, high: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number.")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}.")


@dataclass(frozen=True)
class Site:
    latitude_deg: float = 35.6812
    longitude_deg: float = 139.7671
    elevation_m: float = 40
    name: str = "Tokyo"

    def __post_init__(self):
        bounded("latitude_deg", self.latitude_deg, -90, 90)
        bounded("longitude_deg", self.longitude_deg, -180, 180)
        bounded("elevation_m", self.elevation_m, -500, 9000)


@dataclass(frozen=True)
class Target:
    ra_deg: float
    dec_deg: float
    name: str = "Target"

    def __post_init__(self):
        bounded("ra_deg (ICRS, degrees)", self.ra_deg, 0, 359.999999999)
        bounded("dec_deg (ICRS)", self.dec_deg, -90, 90)


@dataclass(frozen=True)
class Equipment:
    focal_length_mm: float = 400
    sensor_width_mm: float = 23.5
    sensor_height_mm: float = 15.6

    def __post_init__(self):
        for name, value in asdict(self).items():
            bounded(name, value, 0.1, 100000)
        if self.radius_deg > 45:
            raise ValueError("v0.1 supports fields with a diagonal below 90 degrees.")

    @property
    def width_deg(self):
        return math.degrees(2 * math.atan(self.sensor_width_mm / (2 * self.focal_length_mm)))

    @property
    def height_deg(self):
        return math.degrees(2 * math.atan(self.sensor_height_mm / (2 * self.focal_length_mm)))

    @property
    def radius_deg(self):
        return math.degrees(
            math.atan(
                math.hypot(self.sensor_width_mm, self.sensor_height_mm) / (2 * self.focal_length_mm)
            )
        )


@dataclass(frozen=True)
class PlanConfig:
    site: Site
    target: Target
    start: datetime
    end: datetime
    equipment: Equipment = field(default_factory=Equipment)
    exposure_s: float = 60
    readout_s: float = 2
    sample_s: float = 0.5
    padding_s: float = 3
    angular_margin_deg: float = 0.1
    min_target_alt_deg: float = 25
    max_sun_alt_deg: float = -12
    sunlit_only: bool = True
    max_epoch_age_days: float = 7

    def __post_init__(self):
        object.__setattr__(self, "start", utc(self.start))
        object.__setattr__(self, "end", utc(self.end))
        bounded("duration_s", self.duration_s, 1, 86400)
        for name, low, high in [
            ("exposure_s", 0.1, 86400),
            ("readout_s", 0, 3600),
            ("sample_s", 0.05, 2),
            ("padding_s", 0, 3600),
            ("angular_margin_deg", 0, 10),
            ("min_target_alt_deg", 0, 90),
            ("max_sun_alt_deg", -90, 90),
            ("max_epoch_age_days", 0.01, 365),
        ]:
            bounded(name, getattr(self, name), low, high)
        if not isinstance(self.sunlit_only, bool):
            raise ValueError("sunlit_only must be true or false.")
        if self.duration_s / self.sample_s > 350000:
            raise ValueError("Too many time samples. Shorten the session or increase sample_s.")

    @property
    def duration_s(self):
        return (self.end - self.start).total_seconds()

    def to_dict(self):
        result = asdict(self)
        result.update(start=iso(self.start), end=iso(self.end))
        return result

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        data["site"] = Site(**data["site"])
        data["target"] = Target(**data["target"])
        data["equipment"] = Equipment(**data.get("equipment", {}))
        return cls(**data)

    @classmethod
    def load(cls, path: Path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8-sig")))

    def save(self, path: Path):
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )


@dataclass(frozen=True, order=True)
class Interval:
    start_s: float
    end_s: float

    def __post_init__(self):
        if not math.isfinite(self.start_s + self.end_s) or self.end_s < self.start_s:
            raise ValueError("Invalid interval.")


@dataclass(frozen=True)
class Transit:
    norad_id: int
    name: str
    start_s: float
    end_s: float
    epoch_utc: str
    epoch_offset_days: float
    illumination: str


@dataclass
class PlanResult:
    config: PlanConfig
    transits: list[Transit]
    blocked: list[Interval]
    exposures: list[Interval]
    baseline: list[Interval]
    baseline_at_risk: int
    warnings: list[str]
    metadata: dict
