"""Shared UTC event model and geographic calculations."""

from dataclasses import asdict, dataclass
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from typing import Literal

Source = Literal["usgs", "emsc"]
Window = Literal["hour", "day", "week"]
WINDOW_SECONDS: dict[Window, int] = {"hour": 3600, "day": 86400, "week": 604800}


@dataclass(frozen=True)
class Event:
    id: str
    time: datetime
    magnitude: float | None
    depth_km: float
    lat: float
    lon: float
    place: str
    source: Source

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["time"] = self.time.isoformat().replace("+00:00", "Z")
        return result


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance on a mean-radius Earth, including the date line."""
    a, b = radians(lat1), radians(lat2)
    h = sin((b - a) / 2) ** 2 + cos(a) * cos(b) * sin(radians(lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(min(1.0, max(0.0, h))))
