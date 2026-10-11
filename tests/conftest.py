import json
from pathlib import Path

import pytest


@pytest.fixture
def recorded():
    return {
        name: json.loads(
            (Path(__file__).parent / "fixtures" / f"{name}.json").read_text()
        )
        for name in ("usgs", "emsc")
    }
