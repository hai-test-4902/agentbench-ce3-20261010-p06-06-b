"""HTTP retrieval, response cache, and source normalization."""

import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import WINDOW_SECONDS, Event, Source, Window, distance_km


class DataError(ValueError):
    """A provider returned an invalid event response."""


class Client:
    def __init__(
        self,
        cache_dir: Path = Path(".cache/quakewatch"),
        ttl: float = 300,
        no_cache: bool = False,
        timeout: float = 30,
    ) -> None:
        if ttl < 0:
            raise ValueError("cache TTL must be nonnegative")
        self.cache_dir = cache_dir
        self.ttl = ttl
        self.no_cache = no_cache
        self.timeout = timeout

    def _get(self, url: str, key: str) -> dict[str, Any]:
        path = self.cache_dir / (hashlib.sha256(key.encode()).hexdigest() + ".json")
        if not self.no_cache:
            try:
                cached = json.loads(path.read_text())
                age = time.time() - cached["saved_at"]
                if 0 <= age < self.ttl and isinstance(cached["data"], dict):
                    return dict(cached["data"])
            except (OSError, ValueError, TypeError, KeyError):
                pass
        request = Request(url, headers={"User-Agent": "quakewatch/0.1.0"})
        with urlopen(request, timeout=self.timeout) as response:
            data = (
                {"type": "FeatureCollection", "features": []}
                if response.status == 204
                else json.load(response)
            )
        if not isinstance(data, dict) or not isinstance(data.get("features"), list):
            raise DataError("expected a GeoJSON FeatureCollection")
        if not self.no_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            # Atomic replacement prevents readers seeing partial concurrent writes.
            with tempfile.NamedTemporaryFile(
                mode="w", dir=self.cache_dir, delete=False
            ) as temp:
                json.dump({"saved_at": time.time(), "data": data}, temp)
            os.replace(temp.name, path)
        return data

    def events(
        self,
        window: Window = "day",
        source: Literal["usgs", "emsc", "both"] = "both",
        min_mag: float | None = None,
        near: tuple[float, float] | None = None,
        radius_km: float | None = None,
        now: datetime | None = None,
    ) -> list[Event]:
        if (near is None) != (radius_km is None):
            raise ValueError("near and radius_km must be supplied together")
        if radius_km is not None and radius_km < 0:
            raise ValueError("radius_km must be nonnegative")
        now = now or datetime.now(timezone.utc)
        start = now - timedelta(seconds=WINDOW_SECONDS[window])
        sources: list[Source] = ["usgs", "emsc"] if source == "both" else [source]
        events: list[Event] = []
        for provider in sources:
            offset = 1
            while True:
                if provider == "usgs":
                    url = (
                        "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/"
                        f"all_{window}.geojson"
                    )
                else:
                    query = urlencode(
                        {
                            "format": "json",
                            "starttime": start.isoformat(),
                            "endtime": now.isoformat(),
                            "limit": 20000,
                            "offset": offset,
                            "orderby": "time",
                        }
                    )
                    url = "https://www.seismicportal.eu/fdsnws/event/1/query?" + query
                data = self._get(url, f"v1:{provider}:{window}:{offset}")
                events.extend(normalize(data, provider))
                if provider == "usgs" or len(data["features"]) < 20000:
                    break
                offset += 20000
        return sorted(
            (
                event
                for event in events
                if start <= event.time <= now
                and (
                    min_mag is None
                    or (event.magnitude is not None and event.magnitude >= min_mag)
                )
                and (
                    near is None
                    or radius_km is None
                    or distance_km(*near, event.lat, event.lon) <= radius_km
                )
            ),
            key=lambda event: (event.time, event.source, event.id),
            reverse=True,
        )


def normalize(data: dict[str, Any], source: Source) -> list[Event]:
    result: list[Event] = []
    try:
        for feature in data["features"]:
            props = feature["properties"]
            lon, lat, depth = feature["geometry"]["coordinates"]
            if source == "usgs":
                when = datetime.fromtimestamp(props["time"] / 1000, timezone.utc)
                place = props.get("place") or "Unknown"
            else:
                when = datetime.fromisoformat(props["time"].replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                depth = props["depth"]
                place = props.get("flynn_region") or "Unknown"
            result.append(
                Event(
                    id=str(feature["id"]),
                    time=when.astimezone(timezone.utc),
                    magnitude=None if props["mag"] is None else float(props["mag"]),
                    depth_km=float(depth),
                    lat=float(lat),
                    lon=float(lon),
                    place=place,
                    source=source,
                )
            )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise DataError(f"invalid {source} event response: {exc}") from exc
    return result
