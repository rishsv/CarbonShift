"""Carbon source adapter base protocol."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

import pandas as pd


class CarbonSource(Protocol):
    """Protocol that all carbon data adapters must implement."""

    name: str

    def history(self, region: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Return hourly observations for region in [start, end)."""
        ...

    def latest(self, region: str) -> dict:
        """Return the most recent observation for a region."""
        ...

    def mix(self, region: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Return hourly generation mix for region in [start, end)."""
        ...
