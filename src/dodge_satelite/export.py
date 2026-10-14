"""Reviewable UTC exports; includes provenance and limits beside every schedule."""

import csv
import json
from dataclasses import asdict
from datetime import timedelta
from html import escape
from pathlib import Path

from .models import PlanResult, iso


def spreadsheet_text(value):
    # Satellite names are external data. Do not let CSV cells become formulas.
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def export_result(result: PlanResult, directory: Path):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    def timestamp(seconds):
        return iso(result.config.start + timedelta(seconds=seconds))

    with (directory / "exposures.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["exposure", "start_utc", "end_utc", "duration_s", "status"])
        for i, interval in enumerate(result.exposures, 1):
            writer.writerow(
                [
                    i,
                    timestamp(interval.start_s),
                    timestamp(interval.end_s),
                    interval.end_s - interval.start_s,
                    "planned-not-guaranteed-clear",
                ]
            )
    with (directory / "transits.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "norad_id",
                "name",
                "start_utc",
                "end_utc",
                "illumination",
                "epoch_utc",
                "max_epoch_offset_days",
                "padding_s_each_side",
            ]
        )
        for item in result.transits:
            writer.writerow(
                [
                    item.norad_id,
                    spreadsheet_text(item.name),
                    timestamp(item.start_s),
                    timestamp(item.end_s),
                    item.illumination,
                    item.epoch_utc,
                    item.epoch_offset_days,
                    result.config.padding_s,
                ]
            )
    with (directory / "blocked.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["start_utc", "end_utc", "reason"])
        for reason in ("condition_blocked", "satellite_blocked"):
            for item in result.metadata[reason]:
                writer.writerow([timestamp(item["start_s"]), timestamp(item["end_s"]), reason])
    report = {
        "metadata": result.metadata,
        "config": result.config.to_dict(),
        "warnings": result.warnings,
        "summary": {
            "exposure_count": len(result.exposures),
            "integration_s": sum(x.end_s - x.start_s for x in result.exposures),
            "baseline_exposure_count": len(result.baseline),
            "baseline_at_risk": result.baseline_at_risk,
            "transit_count": len(result.transits),
        },
        "exposures": [asdict(x) for x in result.exposures],
        "transits": [asdict(x) for x in result.transits],
    }
    (directory / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (directory / "timeline.svg").write_text(timeline_svg(result), encoding="utf-8")
    return directory


def timeline_svg(result):
    duration = result.config.duration_s
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="320" viewBox="0 0 1200 320">',
        '<rect width="1200" height="320" fill="#111b2c"/>',
        '<g font-family="sans-serif" fill="#e5edf9">',
        '<text x="24" y="30" font-size="20">dodge satelite · planning timeline (UTC)</text>',
        f'<text x="24" y="55">{escape(result.config.target.name)} · {iso(result.config.start)} → {iso(result.config.end)}</text>',
    ]
    rows = [
        ("Conditions", result.metadata["condition_blocked"], "#778195"),
        ("Satellite risk", result.metadata["satellite_blocked"], "#ffae66"),
        ("Exposures", [vars(x) for x in result.exposures], "#62dbbd"),
    ]
    for row, (name, intervals, color) in enumerate(rows):
        y = 95 + row * 55
        parts += [
            f'<text x="24" y="{y + 20}">{name}</text>',
            f'<rect x="160" y="{y}" width="1000" height="30" fill="#263247"/>',
        ]
        for item in intervals:
            x = 160 + 1000 * item["start_s"] / duration
            width = max(0.6, 1000 * (item["end_s"] - item["start_s"]) / duration)
            parts.append(
                f'<rect x="{x:.3f}" y="{y}" width="{width:.3f}" height="30" fill="{color}"/>'
            )
    parts += [
        '<text x="24" y="282">Gray: unsuitable observing conditions · Orange: predicted risk + margin · Green: proposed exposures</text>',
        '<text x="24" y="306">Only the supplied catalog is covered. Read report.json warnings. Clear frames are not guaranteed.</text>',
        "</g></svg>",
    ]
    return "\n".join(parts)
