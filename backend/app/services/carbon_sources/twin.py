"""Twin carbon source adapter — wraps GridDigitalTwin for the CarbonSource protocol."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from app.core.config import load_regions_config
from app.core.time import to_utc
from app.services.grid_twin import get_twin


class TwinSource:
    """CarbonSource adapter using the Grid Digital Twin."""

    name = "twin"

    def __init__(self):
        self._twin = get_twin()
        self._regions = list(load_regions_config().keys())

    def history(self, region: str, start: datetime, end: datetime) -> pd.DataFrame:
        df = self._twin.generate(start, end, regions=[region])
        return df

    def latest(self, region: str) -> dict:
        now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        df = self._twin.generate(now, now + timedelta(hours=1), regions=[region])
        if df.empty:
            return {}
        return df.iloc[0].to_dict()

    def mix(self, region: str, start: datetime, end: datetime) -> pd.DataFrame:
        return self.history(region, start, end)

    def forecast(self, region: str, issued_at: datetime, hours: int = 48) -> pd.DataFrame:
        """Generate a forecast starting from issued_at for `hours` hours."""
        start = to_utc(issued_at).replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=hours)
        return self._twin.generate(start, end, regions=[region])
