# quakewatch

A Python 3.10+ CLI and typed library for recent USGS and EMSC earthquakes.

## Install

Download the wheel from this repository's GitHub Releases, then:

```sh
python3 -m venv .venv
PIP_CACHE_DIR=./.cache/pip .venv/bin/pip install ./quakewatch-0.1.0-py3-none-any.whl
.venv/bin/quakewatch --help
```

Or install a checkout with `PIP_CACHE_DIR=./.cache/pip .venv/bin/pip install .`.

## Usage

```sh
quakewatch list --window day --source both --min-mag 3
quakewatch list --window week --source usgs --near 37.77,-122.42 --radius-km 150
quakewatch list --window hour --cache-ttl 60
quakewatch list --window day --no-cache
quakewatch compare --window day
quakewatch compare --window week --min-mag 4 --no-cache
quakewatch export --window day --source both --format csv --output earthquakes.csv
quakewatch export --window week --min-mag 4 --format json -o earthquakes.json
quakewatch export --window day --format geojson -o earthquakes.geojson
```

All commands support `--window hour|day|week`, `--min-mag`, the paired
`--near LAT,LON --radius-km KM`, `--cache-ttl SECONDS` (default 300),
`--cache-dir PATH` (default `./.cache/quakewatch`), and `--no-cache`.
For negative latitude, use `--near=-33.9,151.2`.
The default window is day and source is both. Both keeps source-specific records;
listing/exporting does not deduplicate them. A missing magnitude is retained unless
a minimum magnitude is requested. Times are UTC and ranges are inclusive.
Rich tables are used on TTYs; redirected output is plain tab-separated text.
Errors go to stderr and exit with status 1; invalid arguments use status 2.

Cache entries store raw responses, expire after the configured TTL, and are replaced
atomically. Repeated EMSC requests use stable window keys despite shifting query
timestamps. Cached results are re-filtered against the current window, but new events
may not appear until expiry. `--no-cache` bypasses reads and writes. An API failure
fails the command rather than silently returning an incomplete combined result.

```python
from quakewatch import Client, export_events
from pathlib import Path

recent = Client(ttl=120).events(window="day", source="both", min_mag=3)
export_events(recent, Path("events.json"), "json")
```

The immutable `Event` model contains `id`, aware UTC `time`, nullable `magnitude`,
`depth_km`, `lat`, `lon`, `place`, and `source`. JSON and CSV share these fields.
GeoJSON adds Point geometry in longitude/latitude/altitude order; altitude is
negative depth in metres, while the property `depth_km` remains in kilometres.

## Comparison

`quakewatch compare --window day` fetches both sources and reports matched and
unmatched counts, followed by both magnitudes and their signed difference
(USGS minus EMSC) for every pair. Unknown magnitudes display `?`.
The library exposes `compare_events(events) -> Comparison`.

A candidate pair must be within **60 seconds and 50 km**, inclusive. Matching is
one-to-one and maximizes the number of pairs; ties are explored deterministically
by time difference, distance, and ID. Dense aftershock sequences remain ambiguous:
this heuristic cannot establish authoritative event identity. Filters apply to
each catalogue before matching, so a magnitude threshold can remove one member
of a potential pair. `compare` always uses both sources.

## Data differences and attribution

[USGS GeoJSON feeds](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php)
provide rolling summary windows, epoch-millisecond times, and depth in kilometres
as the third coordinate. [EMSC FDSN](https://www.seismicportal.eu/fdsn-wsevent.html)
uses `format=json`, ISO timestamps, regional labels, and a separate positive-depth
property (its third coordinate is negative). Quakewatch queries the EMSC time
interval and paginates at 20,000 events. EMSC data: © EMSC, distributed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Catalogues can differ in geographic coverage, reporting latency, location, depth,
magnitude scale and revisions. Missing records do not imply a provider malfunction.
Source IDs are retained and are not interchangeable. These are provisional
observations, not an emergency warning system.

## Development and local verification

```sh
python3 -m venv .venv
PIP_CACHE_DIR=./.cache/pip .venv/bin/pip install -r requirements-check.txt
PIP_CACHE_DIR=./.cache/pip .venv/bin/pip install --no-build-isolation --no-deps -e .
.venv/bin/ruff check src tests scripts
.venv/bin/ruff format --check src tests scripts
.venv/bin/mypy --strict src
.venv/bin/pytest -m 'not integration' --basetemp=.cache/pytest --cov=quakewatch --cov-fail-under=85
python3 scripts/local_checks.py HEAD
```

The local runner requires only Docker, Git and a host Python 3 interpreter. It
archives the specified committed SHA into clean source copies, uses exactly the
three digests in `local-matrix-images.json`, and installs pinned dependencies into
a separate `.venv` in each copy. No host credentials, home directories or Git
configuration are mounted or forwarded. Pip caches remain in `.cache/pip/`.
Each version runs lint, format, strict mypy and mocked unit tests with at least 85%
branch-inclusive coverage. Only 3.12 runs live integration tests, without cache.

Evidence is retained at `artifacts/local-checks/<SHA>/<run-time>/`: an overall
`report.json`, image manifest, per-version logs, `exit-codes.json`, JUnit reports,
`.coverage`, `coverage.json` and `coverage.xml`. A failure exits nonzero; live API
outages count as failures. No GitHub Actions or hosted runners are used.

## Docker

```sh
docker build -t agentbench-quakewatch:local .
docker run --rm agentbench-quakewatch:local list --window day
```

The multi-stage slim image runs as UID/GID 10001 and has a writable `/app` for
its default cache. Dependencies and the package live in `/app/.venv`. The image
contains no source checkout credentials or development tools.

## Releases

Run the local matrix on the PR head before merging, and again on merged main.
Build distributions and the image from that exact merged commit, run the image
smoke test, then tag `v0.1.0`. Upload the locally built sdist and wheel directly
with `gh release create`; download them into a separate directory and compare
SHA-256 values. Keep the matrix, build, smoke, and hash evidence under `artifacts/`.
