from datetime import datetime, timedelta, timezone

import pytest

from quakewatch import Client


@pytest.mark.integration
@pytest.mark.parametrize("source", ["usgs", "emsc"])
def test_live_day(source, tmp_path):
    now = datetime.now(timezone.utc)
    events = Client(tmp_path, no_cache=True).events(
        source=source, window="day", now=now
    )
    assert events, f"{source} unexpectedly returned no events in the past day"
    assert all(event.source == source for event in events)
    assert all(now - timedelta(days=1) <= event.time <= now for event in events)
    assert all(-90 <= event.lat <= 90 and -180 <= event.lon <= 180 for event in events)
