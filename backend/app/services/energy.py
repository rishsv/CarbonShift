"""Energy and power estimation service.

Uses a hardware utilization-based power model:
  P_job = Σ n_i * (idle_i + (max_i - idle_i) * util)
  E_IT   = P_job * duration_h
  E_facility = E_IT * PUE(site, ambient_temp)
  Carbon = Σ_slots E_facility_in_slot * CI(slot)
"""
from __future__ import annotations

import math
from typing import Optional

from app.core.config import load_hardware, load_optimizer_presets, load_sites_config


# ── Hardware profiles (cached) ─────────────────────────────────────────────

def _hw() -> dict:
    return load_hardware()


def gpu_idle_w(gpu_type: str) -> float:
    """Idle watts for a GPU type."""
    return _hw()["gpu_types"].get(gpu_type, {}).get("idle_w", 50.0)


def gpu_max_w(gpu_type: str) -> float:
    """TDP/max watts for a GPU type."""
    return _hw()["gpu_types"].get(gpu_type, {}).get("max_w", 250.0)


def cpu_node_idle_w() -> float:
    return _hw()["cpu_node"]["idle_w"]


def cpu_node_max_w() -> float:
    return _hw()["cpu_node"]["max_w"]


def cpu_cores_per_node() -> int:
    return _hw()["cpu_node"]["cores_per_node"]


# ── PUE model ─────────────────────────────────────────────────────────────

def pue(pue_base: float, pue_k: float, pue_temp_limit_c: float, ambient_temp_c: float) -> float:
    """Temperature-dependent PUE.

    PUE(T) = pue_base + k * max(0, T - temp_limit)
    """
    return pue_base + pue_k * max(0.0, ambient_temp_c - pue_temp_limit_c)


def site_pue(site_id: str, ambient_temp_c: float = 28.0) -> float:
    """Look up site PUE from config."""
    sites = load_sites_config()
    for s in sites:
        if s["id"] == site_id:
            return pue(s["pue_base"], s["pue_k"], s["pue_temp_limit_c"], ambient_temp_c)
    return 1.35  # fallback


# ── Job power model ───────────────────────────────────────────────────────

def power_kw(
    gpus: int,
    gpu_type: Optional[str],
    cpu_cores: int,
    util: float,
) -> float:
    """Estimate job power draw in kW.

    GPU jobs: n_gpu * (idle + (max - idle) * util)
    CPU jobs: n_nodes * (idle + (max - idle) * util)
    """
    total_w = 0.0

    # GPU contribution
    if gpus > 0 and gpu_type:
        idle = gpu_idle_w(gpu_type)
        peak = gpu_max_w(gpu_type)
        total_w += gpus * (idle + (peak - idle) * util)

    # CPU contribution
    if cpu_cores > 0:
        nodes = math.ceil(cpu_cores / cpu_cores_per_node())
        idle = cpu_node_idle_w()
        peak = cpu_node_max_w()
        total_w += nodes * (idle + (peak - idle) * util)

    return total_w / 1000.0  # W → kW


def job_energy_kwh(
    gpus: int,
    gpu_type: Optional[str],
    cpu_cores: int,
    util: float,
    duration_h: float,
    pue_factor: float = 1.35,
) -> tuple[float, float]:
    """Return (IT energy kWh, facility energy kWh) for a job.

    facility_kwh = IT_kwh * PUE
    """
    p_kw = power_kw(gpus, gpu_type, cpu_cores, util)
    it_kwh = p_kw * duration_h
    facility_kwh = it_kwh * pue_factor
    return it_kwh, facility_kwh


def estimate_job(
    gpus: int,
    gpu_type: Optional[str],
    cpu_cores: int,
    util: float,
    duration_h: float,
    site_id: Optional[str] = None,
    ambient_temp_c: float = 28.0,
) -> dict:
    """Full energy estimate for a job. Returns a dict with power_kw and energy_kwh."""
    p_kw = power_kw(gpus, gpu_type, cpu_cores, util)
    pue_factor = site_pue(site_id, ambient_temp_c) if site_id else 1.35
    it_kwh = p_kw * duration_h
    facility_kwh = it_kwh * pue_factor
    return {
        "power_kw": round(p_kw, 3),
        "it_energy_kwh": round(it_kwh, 4),
        "facility_energy_kwh": round(facility_kwh, 4),
        "pue_used": round(pue_factor, 3),
    }


# ── Archetype defaults ────────────────────────────────────────────────────

def archetype_defaults(archetype: str) -> dict:
    """Return default resource parameters for a job archetype."""
    archetypes = _hw().get("archetypes", {})
    return archetypes.get(archetype, {
        "gpu_count": 0,
        "gpu_type": None,
        "cpu_cores": 16,
        "utilization": 0.7,
        "preemptible": False,
        "max_interruptions": 0,
        "typical_duration_h": 1.0,
        "typical_flexibility_h": 4.0,
        "checkpoint_overhead_pct": 0.0,
    })


# ── Carbon per job ────────────────────────────────────────────────────────

def carbon_for_job_g(
    gpus: int,
    gpu_type: Optional[str],
    cpu_cores: int,
    util: float,
    duration_h: float,
    ci_g_per_kwh: float,
    pue_factor: float = 1.35,
) -> float:
    """Estimate total carbon in gCO2e for a job at a given CI.

    carbon_g = facility_kwh * CI
    """
    _, facility_kwh = job_energy_kwh(gpus, gpu_type, cpu_cores, util, duration_h, pue_factor)
    return facility_kwh * ci_g_per_kwh


# ── Slot-level energy (for optimizer) ────────────────────────────────────

def slot_energy_kwh(
    p_kw: float,
    slot_minutes: int,
    pue_factor: float = 1.35,
) -> float:
    """Facility energy for one slot given job power in kW."""
    slot_h = slot_minutes / 60.0
    return p_kw * slot_h * pue_factor


# ── Carbon coefficient for CP-SAT (integer) ───────────────────────────────

CARBON_SCALE = 1  # milligram units: coefficient = round(kWh * 1000 * CI_g_per_kWh)


def carbon_coeff_int(slot_energy_kwh_: float, ci_hat: float) -> int:
    """Integer carbon coefficient for a (job, site, slot) triple.

    Units: milli-gram CO2e.
    Guarded to stay within int32 range by design (see spec 0.6.7).
    """
    val = slot_energy_kwh_ * 1000.0 * ci_hat  # milli-grams
    return max(0, int(round(val)))
