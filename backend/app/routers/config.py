"""Config router — serves YAML config defaults to the UI."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import (
    load_emission_factors,
    load_equivalents,
    load_hardware,
    load_holidays_config,
    load_optimizer_presets,
    load_regions_config,
    load_sites_config,
    load_tariffs,
)

router = APIRouter()


@router.get("/config")
def get_all_config():
    """Return all configuration defaults for the UI."""
    return {
        "emission_factors": load_emission_factors(),
        "hardware": load_hardware(),
        "sites": load_sites_config(),
        "regions": load_regions_config(),
        "tariffs": load_tariffs(),
        "equivalents": load_equivalents(),
        "optimizer_presets": load_optimizer_presets(),
        "holidays": load_holidays_config(),
    }
