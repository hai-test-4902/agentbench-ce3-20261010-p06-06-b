from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from quakewatch import Event, compare_events
from quakewatch.cli import main
from quakewatch.output import show_comparison


def event(id, source, seconds=0, lat=0, lon=0, magnitude=3):
    return Event(
        id,
        datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds),
        magnitude,
        10,
        lat,
        lon,
        id,
        source,
    )


def test_boundary_and_differences(capsys):
    a = event("u", "usgs", magnitude=3.2)
    b = event("e", "emsc", seconds=60, magnitude=2.9)
    result = compare_events([b, a])
    assert len(result.matches) == 1
    assert result.matches[0].magnitude_difference == pytest.approx(0.3)
    assert not result.unmatched_emsc and not result.unmatched_usgs
    show_comparison(result)
    assert "+0.30" in capsys.readouterr().out
    assert not compare_events(
        [a, replace(b, time=b.time + timedelta(microseconds=1))]
    ).matches
    assert (
        len(
            compare_events([a, replace(b, time=a.time - timedelta(seconds=60))]).matches
        )
        == 1
    )
    assert not compare_events([a, replace(b, lon=1)]).matches
    with patch("quakewatch.compare.distance_km", return_value=50):
        assert len(compare_events([a, b]).matches) == 1
    with patch("quakewatch.compare.distance_km", return_value=50.00001):
        assert len(compare_events([a, b]).matches) == 0


def test_maximum_cardinality_and_determinism():
    # u1 can match e1 or e2; u2 can match only e1. Reassignment finds both.
    events = [
        event("u1", "usgs", 0),
        event("u2", "usgs", 60),
        event("e1", "emsc", 0),
        event("e2", "emsc", -60),
    ]
    result = compare_events(events)
    assert {(m.usgs.id, m.emsc.id) for m in result.matches} == {
        ("u1", "e2"),
        ("u2", "e1"),
    }
    assert compare_events(list(reversed(events))) == result
    events.append(event("u3", "usgs", 61))
    result = compare_events(events)
    assert len(result.matches) == 2 and len(result.unmatched_usgs) == 1


def test_missing_magnitude_and_no_matches(capsys):
    for source in ("usgs", "emsc"):
        events = [event("u", "usgs"), event("e", "emsc")]
        events = [
            replace(e, magnitude=None) if e.source == source else e for e in events
        ]
        result = compare_events(events)
        assert result.matches[0].magnitude_difference is None
        show_comparison(result)
        assert "?" in capsys.readouterr().out
    assert compare_events([]).matches == []
    result = compare_events([event("e", "emsc")])
    assert len(result.unmatched_emsc) == 1
    assert not result.unmatched_usgs


def test_compare_cli(capsys):
    with patch(
        "quakewatch.cli.Client.events",
        return_value=[event("u", "usgs"), event("e", "emsc")],
    ):
        assert main(["compare", "--window", "day", "--no-cache"]) == 0
    text = capsys.readouterr().out
    assert "Matched: 1" in text and "Unmatched USGS: 0" in text
    assert "Delta (USGS-EMSC)" in text and "+0.00" in text
    with pytest.raises(SystemExit):
        main(["compare", "--source", "usgs"])
