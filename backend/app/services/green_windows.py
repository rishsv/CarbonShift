"""Green Windows service — finds the best upcoming low-carbon periods."""
from __future__ import annotations

import math
from datetime import datetime

from app.core.config import load_sites_config
from app.core.time import floor_hour_utc, now_utc
from app.schemas import GreenWindow
from app.services.forecaster import get_forecaster


def find_green_windows(
    region: str | None = None,
    hours: int = 12,
    window_h: float = 2.0,
) -> list[GreenWindow]:
    """Find the best consecutive blocks of low carbon intensity.

    Returns the top window per site, ranked by CI reduction vs current CI.
    """
    forecaster = get_forecaster()
    now = floor_hour_utc(now_utc())

    sites = load_sites_config()
    if region:
        sites = [s for s in sites if s["region"] == region]

    # Required consecutive slots (assuming 1h forecast resolution)
    w_slots = math.ceil(window_h)
    if w_slots < 1:
        w_slots = 1

    windows = []

    for s in sites:
        site_id = s["id"]
        reg = s["region"]

        df = forecaster.forecast(reg, now, hours)
        if df.empty or len(df) < w_slots:
            continue

        # Current CI (first row of forecast is roughly 'now')
        current_ci = float(df.iloc[0]["ci_p50"])

        # Moving average over w_slots
        df["ci_ma"] = df["ci_p50"].rolling(window=w_slots).mean()
        df["re_ma"] = df["renewable_share_p50"].rolling(window=w_slots).mean()

        # Find min MA in the horizon (excluding the partial first w_slots-1 rows)
        best_idx = df["ci_ma"].idxmin()
        if type(best_idx) is float and math.isnan(best_idx):
            continue

        best_row = df.loc[best_idx]
        best_ci = float(best_row["ci_ma"])
        best_re = float(best_row["re_ma"])
        
        # Start time is w_slots hours before the end of the window
        start_ts = best_row["target_ts"] - pd.Timedelta(hours=w_slots - 1)
        end_ts = best_row["target_ts"] + pd.Timedelta(hours=1)

        delta_pct = (best_ci - current_ci) / current_ci * 100.0 if current_ci > 0 else 0.0

        windows.append(GreenWindow(
            site_id=site_id,
            region=reg,
            start_ts=start_ts,
            end_ts=end_ts,
            duration_h=float(w_slots),
            avg_ci_p50=round(best_ci, 1),
            avg_renewable_share=round(best_re, 4),
            delta_vs_now_pct=round(delta_pct, 1),
        ))

    # Sort by delta percentage ascending (most negative first = largest drop)
    windows.sort(key=lambda w: w.delta_vs_now_pct)
    return windows

import pandas as pd
