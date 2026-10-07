"""Application configuration loaded from environment variables and YAML configs."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).parent.parent.parent.parent  # carbonshift-ai/
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"
ML_DIR = ROOT_DIR / "ml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    APP_NAME: str = "CarbonShift AI"
    APP_VERSION: str = "0.1.0"
    SEED: int = 42
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = f"sqlite:///{ROOT_DIR}/carbonshift.db"

    # Data source: twin | electricitymaps | replay
    DATA_SOURCE: Literal["twin", "electricitymaps", "replay"] = "twin"

    # External APIs (optional; never called unless enabled)
    ALLOW_EXTERNAL_CALLS: bool = False
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = ""  # empty = use regex fallback
    ELECTRICITYMAPS_TOKEN: str = ""

    # CORS
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    # Solver
    SOLVER_MAX_TIME_SECONDS: int = 15
    SOLVER_NUM_WORKERS: int = 8

    # Slot size
    SLOT_MINUTES: int = 60

    # Paths
    @property
    def config_dir(self) -> Path:
        return CONFIG_DIR

    @property
    def data_dir(self) -> Path:
        return DATA_DIR

    @property
    def ml_dir(self) -> Path:
        return ML_DIR

    @property
    def processed_dir(self) -> Path:
        return DATA_DIR / "processed"

    @property
    def holdout_dir(self) -> Path:
        return DATA_DIR / "holdout"

    @property
    def synthetic_dir(self) -> Path:
        return DATA_DIR / "synthetic"

    @property
    def models_dir(self) -> Path:
        return ML_DIR / "models"

    @property
    def raw_dir(self) -> Path:
        return DATA_DIR / "raw"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ── YAML config loaders ──────────────────────────────────────────────────────

@lru_cache
def load_emission_factors() -> dict:
    with open(CONFIG_DIR / "emission_factors.yaml") as f:
        return yaml.safe_load(f)


@lru_cache
def load_hardware() -> dict:
    with open(CONFIG_DIR / "hardware.yaml") as f:
        return yaml.safe_load(f)


@lru_cache
def load_sites_config() -> list[dict]:
    with open(CONFIG_DIR / "sites.yaml") as f:
        data = yaml.safe_load(f)
    return data["sites"]


@lru_cache
def load_regions_config() -> dict:
    with open(CONFIG_DIR / "regions.yaml") as f:
        data = yaml.safe_load(f)
    return data["regions"]


@lru_cache
def load_tariffs() -> dict:
    with open(CONFIG_DIR / "tariffs.yaml") as f:
        return yaml.safe_load(f)


@lru_cache
def load_equivalents() -> dict:
    with open(CONFIG_DIR / "equivalents.yaml") as f:
        return yaml.safe_load(f)


@lru_cache
def load_optimizer_presets() -> dict:
    with open(CONFIG_DIR / "optimizer_presets.yaml") as f:
        return yaml.safe_load(f)


@lru_cache
def load_holidays_config() -> dict:
    with open(CONFIG_DIR / "holidays_in.yaml") as f:
        return yaml.safe_load(f)


def validate_all_configs() -> dict[str, bool]:
    """Validate all YAML configs can be loaded. Returns {name: ok} dict."""
    results = {}
    loaders = {
        "emission_factors": load_emission_factors,
        "hardware": load_hardware,
        "sites": load_sites_config,
        "regions": load_regions_config,
        "tariffs": load_tariffs,
        "equivalents": load_equivalents,
        "optimizer_presets": load_optimizer_presets,
        "holidays_in": load_holidays_config,
    }
    for name, loader in loaders.items():
        try:
            loader()
            results[name] = True
        except Exception as e:
            results[name] = False
            print(f"[config] ERROR loading {name}: {e}")
    return results
