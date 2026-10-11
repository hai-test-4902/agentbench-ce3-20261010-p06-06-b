"""Deterministic, one-to-one matching between source catalogues."""

from bisect import bisect_left, bisect_right
from collections import deque
from dataclasses import dataclass
from datetime import timedelta

from .models import Event, distance_km


@dataclass(frozen=True)
class Match:
    usgs: Event
    emsc: Event

    @property
    def magnitude_difference(self) -> float | None:
        """USGS magnitude minus EMSC magnitude, or None if either is unknown."""
        if self.usgs.magnitude is None or self.emsc.magnitude is None:
            return None
        return self.usgs.magnitude - self.emsc.magnitude


@dataclass(frozen=True)
class Comparison:
    matches: list[Match]
    unmatched_usgs: list[Event]
    unmatched_emsc: list[Event]


def compare_events(events: list[Event]) -> Comparison:
    """Maximum-cardinality matching with inclusive 60-second / 50-km limits.

    Ties are traversed by time difference, distance, then source ID. Augmenting
    paths avoid losing valid pairs in crowded sequences. This is an association
    heuristic, not a claim of authoritative cross-catalogue event identity.
    """
    usgs = sorted(
        (event for event in events if event.source == "usgs"),
        key=lambda event: (event.time, event.id),
    )
    emsc = sorted(
        (event for event in events if event.source == "emsc"),
        key=lambda event: (event.time, event.id),
    )
    times = [event.time for event in emsc]
    edges: list[list[int]] = []
    for event in usgs:
        start = bisect_left(times, event.time - timedelta(seconds=60))
        end = bisect_right(times, event.time + timedelta(seconds=60))
        candidates = []
        for j in range(start, end):
            other = emsc[j]
            distance = distance_km(event.lat, event.lon, other.lat, other.lon)
            if distance <= 50:
                candidates.append(
                    (
                        abs((event.time - other.time).total_seconds()),
                        distance,
                        other.id,
                        j,
                    )
                )
        edges.append([candidate[3] for candidate in sorted(candidates)])

    left: dict[int, int] = {}
    right: dict[int, int] = {}
    for root in range(len(usgs)):
        queue = deque([root])
        parents: dict[int, int] = {}
        free: int | None = None
        while queue and free is None:
            i = queue.popleft()
            for j in edges[i]:
                if j in parents:
                    continue
                parents[j] = i
                if j not in right:
                    free = j
                    break
                queue.append(right[j])
        while free is not None:
            i = parents[free]
            previous = left.get(i)
            left[i] = free
            right[free] = i
            free = previous
    return Comparison(
        matches=[Match(usgs[i], emsc[j]) for i, j in sorted(left.items())],
        unmatched_usgs=[event for i, event in enumerate(usgs) if i not in left],
        unmatched_emsc=[event for j, event in enumerate(emsc) if j not in right],
    )
