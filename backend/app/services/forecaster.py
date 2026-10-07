"""Forecaster service — wraps ML models or falls back to twin/seasonal-naive."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.core.logging import logger
from app.core.time import floor_hour_utc, to_utc
from app.services.carbon_sources.twin import TwinSource

settings = get_settings()


class Forecaster:
    """Carbon intensity forecaster with ML → twin fallback."""

    def __init__(self):
        self._models: dict[str, object] = {}  # q10/q50/q90
        self._calibration: dict = {}
        self._model_version = "twin-fallback"
        self._twin_source = TwinSource()
        self._try_load_models()

    def _try_load_models(self) -> None:
        """Attempt to load trained LightGBM models from disk."""
        models_dir = settings.models_dir
        for q in ["q10", "q50", "q90"]:
            model_path = models_dir / f"ci_{q}.joblib"
            if model_path.exists():
                try:
                    import joblib
                    self._models[q] = joblib.load(model_path)
                    self._model_version = "lgbm-v1"
                    logger.info(f"Loaded forecaster model {q} from {model_path}")
                except Exception as e:
                    logger.warning(f"Could not load {q} model: {e}")

        cal_path = models_dir / "calibration.json"
        if cal_path.exists():
            with open(cal_path) as f:
                self._calibration = json.load(f)

    def forecast(
        self,
        region: str,
        issued_at: datetime,
        hours: int = 48,
    ) -> pd.DataFrame:
        """Return a forecast DataFrame with columns:
        [target_ts, horizon_h, ci_p10, ci_p50, ci_p90, renewable_share_p50, model_version]
        """
        issued_at_utc = floor_hour_utc(issued_at)

        if self._model_version.startswith("lgbm"):
            return self._ml_forecast(region, issued_at_utc, hours)
        else:
            return self._twin_forecast(region, issued_at_utc, hours)

    def _twin_forecast(self, region: str, issued_at: datetime, hours: int) -> pd.DataFrame:
        """Generate forecast using the Grid Digital Twin with uncertainty from historical spread."""
        start = issued_at
        end = start + timedelta(hours=hours)

        raw_df = self._twin_source.forecast(region, issued_at, hours)
        if raw_df.empty:
            return pd.DataFrame()

        rows = []
        for i, row in raw_df.iterrows():
            ci_p50 = row["ci_g_per_kwh"]
            h = i + 1 if isinstance(i, int) else (row.get("horizon_h", i + 1))

            # Uncertainty grows with horizon: roughly ±5% at h=1, ±20% at h=48
            uncertainty_fraction = 0.05 + 0.15 * (h / 48.0)
            ci_p10 = ci_p50 * (1.0 - uncertainty_fraction)
            ci_p90 = ci_p50 * (1.0 + uncertainty_fraction)

            # Ensure monotonicity
            ci_p10 = min(ci_p10, ci_p50)
            ci_p90 = max(ci_p90, ci_p50)

            rows.append({
                "target_ts": issued_at + timedelta(hours=i),
                "horizon_h": i + 1,
                "ci_p10": round(ci_p10, 1),
                "ci_p50": round(ci_p50, 1),
                "ci_p90": round(ci_p90, 1),
                "renewable_share_p50": round(row.get("renewable_share", 0.3), 4),
                "model_version": self._model_version,
                "is_estimated": True,
            })

        return pd.DataFrame(rows)

    def _ml_forecast(self, region: str, issued_at: datetime, hours: int) -> pd.DataFrame:
        """Generate forecast using trained LightGBM models."""
        from ml.features import build_inference_features  # type: ignore
        try:
            features = build_inference_features(region, issued_at, hours)
            q10_preds = self._models["q10"].predict(features)
            q50_preds = self._models["q50"].predict(features)
            q90_preds = self._models["q90"].predict(features)

            # Apply calibration adjustments if available
            rows = []
            for i in range(hours):
                h = i + 1
                bucket = "1-6" if h <= 6 else ("7-24" if h <= 24 else "25-48")
                cal = self._calibration.get(region, {}).get(bucket, {})

                ci_p10 = float(q10_preds[i]) + cal.get("q10_adj", 0.0)
                ci_p50 = float(q50_preds[i]) + cal.get("q50_adj", 0.0)
                ci_p90 = float(q90_preds[i]) + cal.get("q90_adj", 0.0)

                # Monotonicity
                values = sorted([ci_p10, ci_p50, ci_p90])
                ci_p10, ci_p50, ci_p90 = values

                rows.append({
                    "target_ts": issued_at + timedelta(hours=i),
                    "horizon_h": h,
                    "ci_p10": round(max(0, ci_p10), 1),
                    "ci_p50": round(max(0, ci_p50), 1),
                    "ci_p90": round(max(0, ci_p90), 1),
                    "renewable_share_p50": 0.30,  # TODO: from M4
                    "model_version": self._model_version,
                    "is_estimated": False,
                })
            return pd.DataFrame(rows)
        except Exception as e:
            logger.warning(f"ML forecast failed ({e}); falling back to twin")
            return self._twin_forecast(region, issued_at, hours)

    def accuracy_metrics(self) -> dict:
        """Load and return model accuracy metrics from disk."""
        metrics_path = settings.models_dir / "metrics.json"
        if metrics_path.exists():
            with open(metrics_path) as f:
                return json.load(f)
        return {"model_version": self._model_version, "note": "No metrics file found"}


# ── Module-level singleton ────────────────────────────────────────────────────

_forecaster: Optional[Forecaster] = None


def get_forecaster() -> Forecaster:
    global _forecaster
    if _forecaster is None:
        _forecaster = Forecaster()
    return _forecaster
