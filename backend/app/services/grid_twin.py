"""Grid Digital Twin — physics-informed hourly grid mix and carbon intensity generator.

Implements the 6-step model from the spec:
  1. Regional demand model
  2. Variable renewables from weather
  3. Quasi-fixed sources (hydro, nuclear, other)
  4. Thermal as residual (merit order)
  5. Average carbon intensity
  6. Calibration and noise

Output: hourly DataFrame per region with schema matching CarbonSource protocol.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd

from app.core.config import load_emission_factors, load_holidays_config, load_regions_config
from app.core.logging import logger
from app.core.time import IST, to_ist, to_utc


# ── Constants ─────────────────────────────────────────────────────────────────

# Normalised 24-h demand shape (0=midnight IST). Index = IST hour.
# Values represent fraction of peak demand. Evening peak = 1.0 at hour 20.
BASE_DEMAND_SHAPE = np.array([
    0.72, 0.70, 0.69, 0.68, 0.69, 0.72,  # 0-5 h (night trough)
    0.76, 0.82, 0.87, 0.90, 0.91, 0.92,  # 6-11 h (morning rise)
    0.93, 0.94, 0.95, 0.94, 0.93, 0.95,  # 12-17 h (midday plateau)
    0.97, 0.99, 1.00, 0.98, 0.95, 0.90,  # 18-23 h (evening peak)
], dtype=float)

# Hydro peaking shape (multiplier on monthly CF). Peaking at 18-22h.
HYDRO_HOUR_SHAPE = np.array([
    0.90, 0.88, 0.88, 0.88, 0.89, 0.90,
    0.92, 0.95, 0.98, 1.00, 1.02, 1.04,
    1.05, 1.05, 1.04, 1.03, 1.02, 1.05,
    1.10, 1.15, 1.15, 1.12, 1.05, 0.95,
], dtype=float)


# ── Wind power curve ──────────────────────────────────────────────────────────

def wind_power_curve(v: float, cut_in: float = 3.0, rated: float = 12.0, cut_out: float = 25.0) -> float:
    """Standard 3-parameter wind power curve. Returns CF (0-1)."""
    if v < cut_in or v >= cut_out:
        return 0.0
    if v >= rated:
        return 1.0
    return ((v - cut_in) / (rated - cut_in)) ** 3


# ── Solar model ───────────────────────────────────────────────────────────────

def solar_cf(ghi: float, temp_c: float) -> float:
    """Simple PV CF from GHI (W/m²) and ambient temperature.

    CF = clip(GHI/1000 * (1 - 0.004*(Tcell - 25)), 0, 1) * 0.85 (system derate)
    Tcell = T_ambient + 0.03 * GHI
    """
    if ghi <= 0:
        return 0.0
    t_cell = temp_c + 0.03 * ghi
    raw = (ghi / 1000.0) * (1.0 - 0.004 * (t_cell - 25.0))
    return float(np.clip(raw, 0.0, 1.0)) * 0.85


# ── Synthetic weather generator ───────────────────────────────────────────────

class SyntheticWeather:
    """Deterministic physics-plausible weather series for a location.

    Produces hourly: ghi, temp_c, wind_speed_100m, cloud_cover, precipitation.
    """

    # Regional temperature parameters (lat-based defaults)
    REGION_TEMP_PARAMS = {
        # region: (T_min_annual, T_max_annual)
        "SR": (22.0, 38.0),
        "WR": (18.0, 40.0),
        "NR": (5.0, 45.0),
        "ER": (14.0, 40.0),
        "NER": (8.0, 36.0),
    }

    def __init__(self, lat: float, lon: float, region: str, seed: int = 42):
        self.lat = lat
        self.lon = lon
        self.region = region
        self.rng = np.random.default_rng(seed)

    def generate(self, start: datetime, hours: int) -> pd.DataFrame:
        """Generate a DataFrame with hourly weather for a given period."""
        start_utc = to_utc(start)
        rows = []
        # AR(1) cloud state (persists across hours)
        cloud_state = self.rng.uniform(0.2, 0.6)

        for i in range(hours):
            ts = start_utc + timedelta(hours=i)
            ts_ist = to_ist(ts)
            h = ts_ist.hour
            doy = ts_ist.timetuple().tm_yday  # day of year 1-365
            month = ts_ist.month

            # ── Solar irradiance (clear-sky from lat + declination) ──────────
            decl = math.radians(23.45 * math.sin(math.radians(360 / 365 * (doy - 81))))
            lat_r = math.radians(self.lat)
            hour_angle = math.radians(15 * (h + 0.5 - 12))
            cos_z = (
                math.sin(lat_r) * math.sin(decl)
                + math.cos(lat_r) * math.cos(decl) * math.cos(hour_angle)
            )
            cos_z = max(0.0, cos_z)
            clear_sky_ghi = 1000.0 * cos_z * 0.75  # simple clear-sky (W/m²)

            # Cloud state: AR(1) with monsoon boost
            monsoon_cloud = 0.4 if (month in [6, 7, 8, 9] and self.region in ["SR", "WR", "ER", "NER"]) else 0.15
            cloud_state = (
                0.85 * cloud_state
                + 0.15 * self.rng.uniform(0.1, 0.9)
                + monsoon_cloud * self.rng.uniform(0, 0.2)
            )
            cloud_state = float(np.clip(cloud_state, 0.0, 1.0))
            ghi = clear_sky_ghi * (1.0 - 0.75 * cloud_state)
            ghi += float(self.rng.normal(0, 20))
            ghi = max(0.0, ghi)

            # ── Temperature ──────────────────────────────────────────────────
            t_min, t_max = self.REGION_TEMP_PARAMS.get(self.region, (15.0, 40.0))
            # Annual sine: warmest in May-Jun (doy ~150)
            annual_factor = math.sin(math.radians(360 / 365 * (doy - 30)))
            t_mean = t_min + (t_max - t_min) * (0.5 + 0.5 * annual_factor)
            # Monsoon cooling for non-NR/ER
            if month in [7, 8] and self.region in ["SR", "WR"]:
                t_mean -= 4.0
            # Diurnal: coldest at 5h, warmest at 14h
            diurnal = 8.0 * math.sin(math.radians(180 / 12 * (h - 5)))
            temp_c = t_mean + diurnal + float(self.rng.normal(0, 1.5))

            # ── Wind speed at 100m ────────────────────────────────────────────
            # Base wind: monsoon boost for SR/WR
            base_wind = 5.5 if self.region in ["SR", "WR"] else 3.5
            if month in [6, 7, 8, 9]:
                monsoon_boost = 1.4 if self.region in ["SR", "WR"] else 1.1
            else:
                monsoon_boost = 1.0
            # Diurnal pattern: higher in afternoon
            diurnal_wind = 1.0 + 0.5 * math.sin(math.radians(180 / 12 * (h - 6)))
            wind = base_wind * monsoon_boost * diurnal_wind
            wind += float(self.rng.normal(0, 1.5))
            wind = max(0.0, wind)

            rows.append({
                "ts": ts,
                "ghi_w_m2": ghi,
                "temp_c": temp_c,
                "wind_speed_100m": wind,
                "cloud_cover_frac": cloud_state,
                "precipitation_mm": max(0.0, float(self.rng.normal(0, 2)) * cloud_state),
            })

        return pd.DataFrame(rows)


# ── Grid Digital Twin ─────────────────────────────────────────────────────────

class GridDigitalTwin:
    """Generates hourly regional mix and carbon intensity from weather + calibrated params."""

    def __init__(
        self,
        calibration_k: Optional[float] = None,
        seed: int = 42,
    ):
        self.regions_cfg = load_regions_config()
        self.ef = load_emission_factors()["sources"]
        self.calibration_target = load_emission_factors()["calibration_target_national_ci"]
        self.seed = seed
        self._rng = np.random.default_rng(seed)

        # Calibration scalar on thermal EF (adjusted to match national average)
        self.calibration_k = calibration_k if calibration_k is not None else 1.0

        # Track outage events per region (list of (start_hour_idx, duration, capacity_reduction))
        self._outages: dict[str, list[tuple[int, int, float]]] = {}

        self._holiday_dates: set[str] = self._load_holiday_dates()

    def _load_holiday_dates(self) -> set[str]:
        """Load fixed Indian holidays as YYYY-MM-DD strings."""
        cfg = load_holidays_config()
        dates = set()
        # Add fixed holidays for years 2024-2027
        for year in range(2024, 2028):
            for h in cfg.get("fixed_national_holidays", []):
                dates.add(f"{year}-{h['month']:02d}-{h['day']:02d}")
        return dates

    def _is_holiday(self, dt: datetime) -> bool:
        """Check if a datetime (in IST) falls on a holiday."""
        dt_ist = to_ist(dt)
        date_str = dt_ist.strftime("%Y-%m-%d")
        if date_str in self._holiday_dates:
            return True
        # Check weekday holidays via the holidays package if available
        try:
            import holidays as hdays
            in_holidays = hdays.country_holidays("IN")
            return dt_ist.date() in in_holidays
        except ImportError:
            pass
        return False

    def _demand_factor(self, dt: datetime, region: str) -> float:
        """Compute the demand multiplier for a given time."""
        cfg = self.regions_cfg[region]
        dt_ist = to_ist(dt)
        h = dt_ist.hour
        month = dt_ist.month
        weekday = dt_ist.weekday()

        base_shape = BASE_DEMAND_SHAPE[h]
        seasonal = cfg["seasonal_factor"][month - 1]

        # Weekend / holiday factors
        hol_cfg = load_holidays_config()
        if self._is_holiday(dt):
            day_factor = hol_cfg.get("holiday_demand_factor", 0.90)
        elif weekday >= 5:  # Sat/Sun
            day_factor = hol_cfg.get("weekend_demand_factor", 0.93)
        else:
            day_factor = 1.0

        # Festival boost (Oct-Nov)
        fest = hol_cfg.get("festival_demand_boost", {})
        fest_months = fest.get("months", [])
        fest_factor = fest.get("factor", 1.0) if month in fest_months else 1.0

        return base_shape * seasonal * day_factor * fest_factor

    def _temperature_sensitivity(self, region: str, temp_c: float) -> float:
        """Demand increase factor from temperature."""
        cfg = self.regions_cfg[region]
        sens = cfg.get("temp_sensitivity_pct_per_c", 1.5) / 100.0
        return 1.0 + sens * max(0.0, temp_c - 26.0) / 10.0

    def generate_region_hour(
        self,
        dt: datetime,
        region: str,
        weather: dict,
        noise_state: Optional[dict] = None,
    ) -> dict:
        """Generate one hourly observation for a region.

        Args:
            dt: UTC datetime (hour start)
            region: region code
            weather: dict with ghi_w_m2, temp_c, wind_speed_100m
            noise_state: optional mutable dict for AR(1) noise continuity

        Returns:
            Dict with columns matching the GridObservation schema.
        """
        cfg = self.regions_cfg[region]
        dt_ist = to_ist(dt)
        h = dt_ist.hour
        month = dt_ist.month

        cap = cfg["installed_capacity_gw"]  # GW
        peak_demand = cfg["peak_demand_gw"]

        # ── 1. Demand ─────────────────────────────────────────────────────────
        base_factor = self._demand_factor(dt, region)
        temp_factor = self._temperature_sensitivity(region, weather.get("temp_c", 28.0))
        demand_gw = peak_demand * base_factor * temp_factor

        # ── 2. Solar ─────────────────────────────────────────────────────────
        cf_solar = solar_cf(weather.get("ghi_w_m2", 0.0), weather.get("temp_c", 28.0))
        solar_gw = cap["solar"] * cf_solar

        # ── 3. Wind ──────────────────────────────────────────────────────────
        wind_v = weather.get("wind_speed_100m", 5.0)
        # Monsoon boost for qualifying regions
        wind_boost = cfg.get("wind_monsoon_boost", {})
        if month in wind_boost.get("months", []):
            wind_v *= wind_boost.get("multiplier", 1.0)
        cf_wind = wind_power_curve(wind_v) * 0.90  # availability derate
        wind_gw = cap["wind"] * cf_wind

        # ── 4. Hydro ─────────────────────────────────────────────────────────
        hydro_cf_month = cfg["hydro_cf_by_month"][month - 1]
        hydro_hour_mult = HYDRO_HOUR_SHAPE[h]
        hydro_gw = cap["hydro"] * hydro_cf_month * hydro_hour_mult

        # ── 5. Nuclear and other (quasi-fixed) ───────────────────────────────
        nuclear_gw = cap["nuclear"] * 0.80
        other_gw = cap["other"] * 0.50

        # ── 6. Thermal as residual ────────────────────────────────────────────
        residual = demand_gw - (solar_gw + wind_gw + hydro_gw + nuclear_gw + other_gw)
        # Clamp thermal to available capacity (85% availability)
        thermal_cap = cap["thermal"] * 0.85

        # Apply any active outages
        if noise_state and "outage_reduction" in noise_state:
            thermal_cap *= (1.0 - noise_state.get("outage_reduction", 0.0))

        thermal_gw = float(np.clip(residual, 0.0, thermal_cap))
        curtailed_solar_gw = max(0.0, -residual)  # if residual < 0, excess solar curtailed

        # Import if thermal insufficient
        import_gw = max(0.0, residual - thermal_cap)
        if import_gw > 0:
            import_gw = min(import_gw, demand_gw * 0.10)  # cap at 10% of demand

        gas_share = cfg.get("gas_share_thermal", 0.07)
        coal_gw = thermal_gw * (1.0 - gas_share)
        gas_gw = thermal_gw * gas_share

        # ── AR(1) noise on generation components ─────────────────────────────
        if noise_state is not None:
            # Update AR(1) state
            noise_state["phi"] = noise_state.get("phi", 0.0)
            noise_state["phi"] = 0.9 * noise_state["phi"] + 0.02 * float(
                np.random.default_rng(self.seed + int(dt.timestamp()) % 100000).normal(0, 1)
            )
            noise_mult = 1.0 + noise_state["phi"]
            solar_gw *= noise_mult
            wind_gw = max(0.0, wind_gw * noise_mult)

        # ── 7. Total generation and carbon intensity ──────────────────────────
        total_gen = solar_gw + wind_gw + hydro_gw + nuclear_gw + other_gw + coal_gw + gas_gw + import_gw
        if total_gen <= 0:
            total_gen = demand_gw + 1e-6

        ef = self.ef
        coal_ef = ef["coal"]["gco2e_per_kwh"] * self.calibration_k
        gas_ef = ef["gas"]["gco2e_per_kwh"]
        solar_ef = ef["solar"]["gco2e_per_kwh"]
        wind_ef = ef["wind"]["gco2e_per_kwh"]
        hydro_ef = ef["hydro"]["gco2e_per_kwh"]
        nuclear_ef = ef["nuclear"]["gco2e_per_kwh"]
        other_ef = ef["other"]["gco2e_per_kwh"]
        # Import assumed average national intensity (simplified)
        import_ef = self.calibration_target

        total_emission = (
            coal_gw * coal_ef
            + gas_gw * gas_ef
            + solar_gw * solar_ef
            + wind_gw * wind_ef
            + hydro_gw * hydro_ef
            + nuclear_gw * nuclear_ef
            + other_gw * other_ef
            + import_gw * import_ef
        )
        ci = total_emission / total_gen  # gCO2e/kWh (GW / GW = dimensionless; EF in gCO2/kWh)

        # Mix shares
        renewable_gw = solar_gw + wind_gw + hydro_gw

        return {
            "ts": dt,
            "region": region,
            "ci_g_per_kwh": round(ci, 1),
            "share_solar": round(solar_gw / total_gen, 4),
            "share_wind": round(wind_gw / total_gen, 4),
            "share_hydro": round(hydro_gw / total_gen, 4),
            "share_nuclear": round(nuclear_gw / total_gen, 4),
            "share_thermal": round((coal_gw + gas_gw) / total_gen, 4),
            "share_other": round((other_gw + import_gw) / total_gen, 4),
            "renewable_share": round(renewable_gw / total_gen, 4),
            "demand_mw": round(demand_gw * 1000, 1),
            "solar_gw": round(solar_gw, 3),
            "wind_gw": round(wind_gw, 3),
            "source": "twin",
            "is_estimated": True,
        }

    def generate(
        self,
        start: datetime,
        end: datetime,
        regions: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """Generate a full hourly DataFrame for [start, end) for all (or specified) regions."""
        if regions is None:
            regions = list(self.regions_cfg.keys())

        start_utc = to_utc(start)
        end_utc = to_utc(end)

        hours = int((end_utc - start_utc).total_seconds() / 3600)
        logger.info(f"GridTwin: generating {hours}h × {len(regions)} regions from {start_utc.date()}")

        all_rows = []
        for region in regions:
            cfg = self.regions_cfg[region]
            synth_weather = SyntheticWeather(
                lat=cfg["representative_lat"],
                lon=cfg["representative_lon"],
                region=region,
                seed=self.seed + hash(region) % 1000,
            )
            weather_df = synth_weather.generate(start_utc, hours)
            noise_state: dict = {}

            for i in range(hours):
                ts = start_utc + timedelta(hours=i)
                w_row = weather_df.iloc[i]
                row = self.generate_region_hour(
                    dt=ts,
                    region=region,
                    weather={
                        "ghi_w_m2": w_row["ghi_w_m2"],
                        "temp_c": w_row["temp_c"],
                        "wind_speed_100m": w_row["wind_speed_100m"],
                    },
                    noise_state=noise_state,
                )
                all_rows.append(row)

        df = pd.DataFrame(all_rows)
        return df

    def calibrate(self, df: pd.DataFrame, target_ci: Optional[float] = None) -> float:
        """Binary-search for calibration_k to match national annual mean CI.

        Returns the calibrated k value.
        """
        target = target_ci or self.calibration_target
        # Compute current national weighted mean CI
        current_mean = df["ci_g_per_kwh"].mean()
        if current_mean <= 0:
            return self.calibration_k

        # Simple linear scaling first approximation
        ratio = target / current_mean
        logger.info(f"Calibration: target={target}, current={current_mean:.1f}, ratio={ratio:.3f}")
        self.calibration_k *= ratio
        return self.calibration_k


# ── Module-level singleton ────────────────────────────────────────────────────

_twin: Optional[GridDigitalTwin] = None


def get_twin() -> GridDigitalTwin:
    global _twin
    if _twin is None:
        _twin = GridDigitalTwin()
    return _twin
