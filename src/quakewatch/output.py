"""Terminal presentation and portable exports."""

import csv
import json
import sys
from pathlib import Path
from typing import TextIO

from rich.console import Console
from rich.table import Table

from .models import Event


def table(headers: list[str], rows: list[list[str]], stream: TextIO) -> None:
    if stream.isatty():
        display = Table(*headers)
        for row in rows:
            display.add_row(*row)
        Console(file=stream, markup=False).print(display)
    else:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(headers)
        writer.writerows(rows)


def show_events(events: list[Event]) -> None:
    table(
        ["ID", "Time (UTC)", "Mag", "Depth km", "Lat", "Lon", "Place", "Source"],
        [
            [
                event.id,
                str(event.to_dict()["time"]),
                "?" if event.magnitude is None else f"{event.magnitude:g}",
                f"{event.depth_km:g}",
                f"{event.lat:g}",
                f"{event.lon:g}",
                event.place,
                event.source,
            ]
            for event in events
        ],
        sys.stdout,
    )


def export_events(events: list[Event], path: Path, format: str) -> None:
    if format not in {"csv", "json", "geojson"}:
        raise ValueError("format must be csv, json, or geojson")
    with path.open("w", encoding="utf-8", newline="") as out:
        if format == "csv":
            writer = csv.DictWriter(out, fieldnames=list(Event.__dataclass_fields__))
            writer.writeheader()
            writer.writerows(event.to_dict() for event in events)
        elif format == "json":
            json.dump([event.to_dict() for event in events], out, indent=2)
        else:
            json.dump(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "id": f"{event.source}:{event.id}",
                            "properties": event.to_dict(),
                            "geometry": {
                                "type": "Point",
                                # GeoJSON altitude: metres above the surface.
                                "coordinates": [
                                    event.lon,
                                    event.lat,
                                    -1000 * event.depth_km,
                                ],
                            },
                        }
                        for event in events
                    ],
                },
                out,
                indent=2,
            )
        out.write("\n")
