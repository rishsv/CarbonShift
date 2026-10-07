"""
Electricity Maps live carbon intensity fetcher for Indian grid regions.
API docs: https://docs.electricitymaps.com/
Free non-commercial key: https://api-portal.electricitymaps.com/

Region → Electricity Maps zone mapping for India:
  NR (Northern)  → IN-NO
  WR (Western)   → IN-WE  
  SR (Southern)  → IN-SO
  ER (Eastern)   → IN-EA
  NER (NE)       → IN-EA  (proxy — NER not separately tracked)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

logger = logging.getLogger("carbonshift")

ZONE_MAP = {
    "NR":  "IN-NO",
    "WR":  "IN-WE",
    "SR":  "IN-SO",
    "ER":  "IN-EA",
    "NER": "IN-EA",  # Proxy
}

BASE_URL = "https://api.electricitymap.org/v3"


class ElectricityMapsClient:
    """Client for Electricity Maps API — live carbon intensity for Indian grid."""

    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "auth-token": token,
            "Content-Type": "application/json",
        })

    def get_carbon_intensity_now(self, region: str) -> Optional[dict]:
        """Get current carbon intensity for a region. Returns None on failure."""
        zone = ZONE_MAP.get(region, "IN-SO")
        try:
            resp = self.session.get(
                f"{BASE_URL}/carbon-intensity/latest",
                params={"zone": zone},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            ci = data.get("carbonIntensity")  # g CO2eq / kWh
            if ci is None:
                return None
            return {
                "region": region,
                "zone": zone,
                "ci_g_per_kwh": float(ci),
                "ts": data.get("datetime", datetime.now(timezone.utc).isoformat()),
                "source": "electricitymaps",
                "is_estimated": data.get("isEstimated", True),
                "estimation_method": data.get("estimationMethod", ""),
            }
        except Exception as e:
            logger.warning(f"ElectricityMaps live fetch failed for {region}: {e}")
            return None

    def get_power_breakdown_now(self, region: str) -> Optional[dict]:
        """Get current power generation breakdown."""
        zone = ZONE_MAP.get(region, "IN-SO")
        try:
            resp = self.session.get(
                f"{BASE_URL}/power-breakdown/latest",
                params={"zone": zone},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            breakdown = data.get("powerConsumptionBreakdown", {})
            total = sum(breakdown.values()) or 1
            
            renewables = ["solar", "wind", "hydro", "nuclear", "geothermal", "biomass"]
            renewable_mw = sum(breakdown.get(r, 0) for r in renewables)
            
            return {
                "region": region,
                "zone": zone,
                "ts": data.get("datetime", datetime.now(timezone.utc).isoformat()),
                "share_solar":   breakdown.get("solar", 0) / total,
                "share_wind":    breakdown.get("wind", 0) / total,
                "share_hydro":   breakdown.get("hydro", 0) / total,
                "share_nuclear": breakdown.get("nuclear", 0) / total,
                "share_thermal": (breakdown.get("coal", 0) + breakdown.get("gas", 0) + breakdown.get("oil", 0)) / total,
                "renewable_share": renewable_mw / total,
                "demand_mw": data.get("powerConsumptionTotal", 0),
                "source": "electricitymaps",
            }
        except Exception as e:
            logger.warning(f"ElectricityMaps power breakdown failed for {region}: {e}")
            return None

    def get_carbon_intensity_history(
        self, region: str, start: datetime, end: datetime
    ) -> list[dict]:
        """Get hourly historical carbon intensity. Returns [] on failure."""
        zone = ZONE_MAP.get(region, "IN-SO")
        rows = []
        try:
            resp = self.session.get(
                f"{BASE_URL}/carbon-intensity/history",
                params={
                    "zone": zone,
                    "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            for entry in data.get("history", []):
                ci = entry.get("carbonIntensity")
                if ci is not None:
                    rows.append({
                        "ts": entry["datetime"],
                        "region": region,
                        "ci_g_per_kwh": float(ci),
                        "source": "electricitymaps",
                        "is_estimated": entry.get("isEstimated", True),
                    })
        except Exception as e:
            logger.warning(f"ElectricityMaps history fetch failed for {region}: {e}")
        return rows


# ── Module singleton ──────────────────────────────────────────────────────────

_client: Optional[ElectricityMapsClient] = None


def get_em_client() -> Optional[ElectricityMapsClient]:
    """Return the EM client if token is configured, else None."""
    global _client
    if _client is not None:
        return _client
    from app.core.config import get_settings
    token = get_settings().ELECTRICITYMAPS_TOKEN
    if not token:
        return None
    _client = ElectricityMapsClient(token)
    return _client
