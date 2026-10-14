import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path

from . import __version__
from .catalog import fetch_catalog, local_catalog
from .export import export_result
from .models import PlanConfig
from .predict import plan


def demo_inputs():
    root = files("dodge_satelite").joinpath("data")
    config = PlanConfig.from_dict(
        json.loads(root.joinpath("demo.json").read_text(encoding="utf-8"))
    )
    from .catalog import parse_csv

    catalog = parse_csv(
        root.joinpath("demo.csv").read_text(encoding="utf-8"),
        "BUNDLED SYNTHETIC DEMO (not current orbital data)",
    )
    catalog.warnings.append(
        "DEMO: synthetic historical satellite and pointing, for software demonstration only."
    )
    return config, catalog


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="dodge satelite — satellite-aware exposure planning"
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Run the bundled offline, synthetic demonstration")
    demo.add_argument("--out", type=Path, default=Path("reports/demo"))
    run = commands.add_parser("plan", help="Calculate from a JSON observation profile")
    run.add_argument("config", type=Path)
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--catalog", type=Path, help="Local CelesTrak GP/OMM CSV")
    source.add_argument(
        "--group", help="CelesTrak group, e.g. visual or stations (incomplete subsets)"
    )
    run.add_argument("--offline", action="store_true", help="For --group, read cache only")
    run.add_argument("--cache-dir", type=Path)
    run.add_argument("--out", type=Path, default=Path("reports/plan"))
    fetch = commands.add_parser(
        "fetch", help="Fetch/cache a CelesTrak GP group; two-hour minimum refresh"
    )
    fetch.add_argument("--group", default="visual")
    fetch.add_argument("--cache-dir", type=Path)
    fetch.add_argument("--offline", action="store_true")
    commands.add_parser("gui", help="Open the desktop application")
    commands.add_parser("nina-bridge", help="N.I.N.A. plugin stdio protocol (one JSON request)")
    migrate = commands.add_parser(
        "migrate-nina", help="Copy a saved NINA sequence for current DLL names"
    )
    migrate.add_argument("source", type=Path)
    migrate.add_argument("--out", type=Path, required=True)
    migrate.add_argument(
        "--bundled-engine",
        action="store_true",
        help="Reset instruction engine overrides to the bundled engine",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "migrate-nina":
            from .migrate import migrate_file

            count = migrate_file(args.source, args.out, args.bundled_engine)
            print(f"Updated {count} instruction references. Original unchanged; inspect {args.out}")
            return 0
        if args.command == "nina-bridge":
            from .nina_bridge import main as bridge_main

            return bridge_main()
        if args.command == "gui":
            from .gui import main as gui_main

            return gui_main()
        if args.command == "fetch":
            catalog = fetch_catalog(args.group, args.cache_dir, args.offline)
            print(
                f"{len(catalog.satellites)} satellites; downloaded: {catalog.fetched_at}; SHA256: {catalog.sha256}"
            )
            for warning in catalog.warnings:
                print("WARNING: " + warning, file=sys.stderr)
            return 0
        if args.command == "demo":
            config, catalog = demo_inputs()
        else:
            config = PlanConfig.load(args.config)
            catalog = (
                local_catalog(args.catalog)
                if args.catalog
                else fetch_catalog(args.group, args.cache_dir, args.offline)
            )
        result = plan(config, catalog)
        export_result(result, args.out)
        print(
            f"{len(result.transits)} predicted crossings; {len(result.exposures)} planned exposures; "
            f"baseline risk: {result.baseline_at_risk}/{len(result.baseline)}"
        )
        print(f"UTC CSVs, timeline and provenance: {args.out.resolve()}")
        for warning in result.warnings:
            print("WARNING: " + warning, file=sys.stderr)
        return 0
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
