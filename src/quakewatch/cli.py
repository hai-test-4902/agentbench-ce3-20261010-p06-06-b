"""Command-line entry point."""

import argparse
import math
import sys
from pathlib import Path
from urllib.error import URLError

from .client import Client
from .output import export_events, show_events


def finite(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError("must be finite")
    return number


def coordinates(value: str) -> tuple[float, float]:
    try:
        lat, lon = (finite(part) for part in value.split(","))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError
    except (ValueError, argparse.ArgumentTypeError) as exc:
        raise argparse.ArgumentTypeError("use LAT,LON in valid degree ranges") from exc
    return lat, lon


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="quakewatch")
    root.add_argument("--version", action="version", version="quakewatch 0.1.0")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("list", "export"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--window", choices=("hour", "day", "week"), default="day")
        cmd.add_argument("--source", choices=("usgs", "emsc", "both"), default="both")
        cmd.add_argument("--min-mag", type=finite)
        cmd.add_argument("--near", type=coordinates)
        cmd.add_argument("--radius-km", type=finite)
        cmd.add_argument("--cache-ttl", type=finite, default=300, metavar="SECONDS")
        cmd.add_argument("--cache-dir", type=Path, default=Path(".cache/quakewatch"))
        cmd.add_argument("--no-cache", action="store_true")
        if name == "export":
            cmd.add_argument(
                "--format", choices=("csv", "json", "geojson"), required=True
            )
            cmd.add_argument("--output", "-o", type=Path, required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    root = parser()
    args = root.parse_args(argv)
    try:
        client = Client(args.cache_dir, args.cache_ttl, args.no_cache)
        events = client.events(
            args.window, args.source, args.min_mag, args.near, args.radius_km
        )
        if args.command == "export":
            export_events(events, args.output, args.format)
        else:
            show_events(events)
    except (OSError, ValueError, URLError) as exc:
        print(f"quakewatch: {exc}", file=sys.stderr)
        return 1
    return 0
