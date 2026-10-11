import copy
import csv
import io
import json
import runpy
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

from quakewatch import Client, DataError, distance_km, export_events
from quakewatch.cli import main
from quakewatch.client import normalize
from quakewatch.output import show_events, table


def response(data, status=200):
    result = io.BytesIO(json.dumps(data).encode())
    result.status = status
    return result


def test_recorded_normalization(recorded):
    usgs = normalize(recorded["usgs"], "usgs")
    emsc = normalize(recorded["emsc"], "emsc")
    assert len(usgs) == recorded["usgs"]["metadata"]["count"]
    assert usgs[0].id == "ci41346279"
    assert usgs[0].magnitude == 0.94
    assert usgs[0].time.tzinfo == timezone.utc
    assert usgs[0].depth_km == 1.48
    assert emsc[0].time == datetime(2026, 10, 11, 0, 0, 17, 113000, timezone.utc)
    assert emsc[0].depth_km == 10
    assert emsc[0].lat == 50.0997
    assert emsc[0].place == "POLAND"
    assert emsc[0].to_dict()["time"].endswith("Z")


def test_nulls_and_naive_time(recorded):
    data = copy.deepcopy(recorded["emsc"])
    data["features"][0]["properties"].update(
        mag=None, time="2026-10-11T00:00:00", flynn_region=None
    )
    event = normalize(data, "emsc")[0]
    assert event.magnitude is None
    assert event.place == "Unknown"
    assert event.time.tzinfo == timezone.utc
    with pytest.raises(DataError, match="invalid usgs"):
        normalize({"features": [{}]}, "usgs")


def test_distances():
    assert distance_km(0, 0, 0, 0) == 0
    assert distance_km(0, 179.9, 0, -179.9) == pytest.approx(22.239, abs=0.001)
    assert distance_km(0, 0, 0, 180) == pytest.approx(20015.114, abs=0.01)


def test_cache(tmp_path, recorded):
    client = Client(tmp_path, ttl=60)
    data = recorded["usgs"]
    with patch("quakewatch.client.urlopen", return_value=response(data)) as http:
        assert client._get("https://example.test/a", "key") == data
        assert client._get("https://example.test/b", "key") == data
        http.assert_called_once()
    path = next(tmp_path.glob("*.json"))
    path.write_text("bad json")
    with patch("quakewatch.client.urlopen", return_value=response(data)) as http:
        client._get("https://example.test/a", "key")
        http.assert_called_once()
    cached = json.loads(path.read_text())
    cached["saved_at"] = 0
    path.write_text(json.dumps(cached))
    with patch("quakewatch.client.urlopen", return_value=response(data)) as http:
        client._get("https://example.test/a", "key")
        http.assert_called_once()
    before = path.read_bytes()
    with patch("quakewatch.client.urlopen", return_value=response(data)) as http:
        Client(tmp_path, no_cache=True)._get("https://example.test/a", "key")
        http.assert_called_once()
    assert path.read_bytes() == before


def test_http_errors_and_empty(tmp_path):
    client = Client(tmp_path, no_cache=True)
    with patch("quakewatch.client.urlopen", return_value=response(None, 204)):
        assert client._get("https://example.test", "k")["features"] == []
    with patch("quakewatch.client.urlopen", return_value=response([])):
        with pytest.raises(DataError):
            client._get("https://example.test", "k")
    with patch("quakewatch.client.urlopen", side_effect=URLError("offline")):
        with pytest.raises(URLError):
            client.events()
    assert not list(tmp_path.iterdir())


def test_filters_and_cache_keys(recorded, tmp_path):
    client = Client(tmp_path)
    now = datetime(2026, 10, 11, 0, 15, tzinfo=timezone.utc)
    with patch.object(
        client, "_get", side_effect=lambda url, key: recorded[key.split(":")[1]]
    ) as get:
        events = client.events(now=now)
        assert {event.source for event in events} == {"usgs", "emsc"}
        assert events == sorted(events, key=lambda event: event.time, reverse=True)
        assert "format=json" in get.call_args.args[0]
        assert "offset=1" in get.call_args.args[0]
        filtered = client.events(
            source="emsc", min_mag=2, near=(50.1, 19.3), radius_km=5, now=now
        )
        assert len(filtered) == 1
        assert filtered[0].place == "POLAND"
        assert client.events(source="emsc", min_mag=3, now=now) == []
        assert (
            client.events(source="emsc", window="hour", now=now + timedelta(days=2))
            == []
        )
    with pytest.raises(ValueError):
        client.events(near=(0, 0))
    with pytest.raises(ValueError):
        client.events(radius_km=3)
    with pytest.raises(ValueError):
        client.events(near=(0, 0), radius_km=-1)
    with pytest.raises(ValueError):
        Client(ttl=-1)


def test_pagination(recorded):
    client = Client(no_cache=True)
    first = {"features": [recorded["emsc"]["features"][0]] * 20000}
    with patch.object(client, "_get", side_effect=[first, {"features": []}]) as get:
        assert (
            len(
                client.events(
                    source="emsc", now=datetime(2026, 10, 11, 1, tzinfo=timezone.utc)
                )
            )
            == 20000
        )
        assert "offset=20001" in get.call_args.args[0]


@pytest.mark.parametrize("format", ["csv", "json", "geojson"])
def test_export(format, tmp_path, recorded):
    events = normalize(recorded["emsc"], "emsc")
    path = tmp_path / ("events." + format)
    export_events(events, path, format)
    if format == "csv":
        with path.open() as stream:
            data = list(csv.DictReader(stream))
        assert data[0]["id"] == events[0].id
    elif format == "json":
        assert json.loads(path.read_text())[0] == events[0].to_dict()
    else:
        data = json.loads(path.read_text())
        assert data["features"][0]["geometry"]["coordinates"] == [
            19.3089,
            50.0997,
            -10000,
        ]
    export_events([], path, format)
    assert path.read_text()
    with pytest.raises(ValueError):
        export_events(events, path, "xml")


def test_output(recorded, capsys):
    data = recorded["usgs"]
    data["features"][0]["properties"]["mag"] = None
    show_events(normalize(data, "usgs"))
    output = capsys.readouterr().out
    assert "Time (UTC)" in output and "?" in output and "\x1b" not in output
    stream = MagicMock()
    stream.isatty.return_value = True
    with patch("quakewatch.output.Console") as console:
        table(["ID"], [["a"]], stream)
        console.return_value.print.assert_called_once()


def test_cli(recorded, capsys, tmp_path):
    events = normalize(recorded["emsc"], "emsc")
    with patch("quakewatch.cli.Client.events", return_value=events):
        assert main(["list", "--no-cache", "--near", "50,19", "--radius-km", "10"]) == 0
        assert "POLAND" in capsys.readouterr().out
        path = tmp_path / "events.json"
        assert main(["export", "--format", "json", "-o", str(path)]) == 0
        assert len(json.loads(path.read_text())) == 2
        with patch.object(sys, "argv", ["quakewatch", "list"]):
            with pytest.raises(SystemExit) as exit:
                runpy.run_module("quakewatch", run_name="__main__")
            assert exit.value.code == 0
    with patch("quakewatch.cli.Client.events", side_effect=URLError("offline")):
        assert main(["list"]) == 1
        assert "offline" in capsys.readouterr().err
    assert main(["list", "--cache-ttl", "-1"]) == 1


@pytest.mark.parametrize(
    "args",
    [
        ["list", "--near", "100,0"],
        ["list", "--near", "abc"],
        ["list", "--min-mag", "nan"],
        ["list", "--radius-km", "inf"],
        ["export"],
        ["list", "--window", "month"],
    ],
)
def test_cli_invalid(args):
    with pytest.raises(SystemExit) as exit:
        main(args)
    assert exit.value.code == 2
