"""
ML training pipeline — generates synthetic data and trains LightGBM quantile models.
Run from: d:/Carbon Shift/carbonshift-ai/ 
  python ml/scripts/run_pipeline.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Allow importing app + ml modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.carbon_sources.twin import TwinSource

settings = get_settings()

# ── 1. Generate synthetic data ────────────────────────────────────────────────

def generate_data(days: int = 365) -> pd.DataFrame:
    source = TwinSource()
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    print(f"Generating {days}d from {start.date()} → {end.date()} …")

    dfs = []
    for region in ["NR", "WR", "SR", "ER", "NER"]:
        df = source.history(region, start, end)
        df["region"] = region
        dfs.append(df)
        print(f"  {region}: {len(df)} rows")

    combined = pd.concat(dfs, ignore_index=True)
    out = settings.raw_dir / "synthetic_history.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(out, index=False)
    print(f"  Saved {len(combined)} rows → {out}")
    return combined


# ── 2. Feature engineering ────────────────────────────────────────────────────

REGION_MAP = {"NR": 0, "WR": 1, "SR": 2, "ER": 3, "NER": 4}

def build_features(df: pd.DataFrame):
    df = df.copy()
    # Ensure ts is tz-aware
    if "ts" not in df.columns:
        raise ValueError("DataFrame must have a 'ts' column")
    df["ts"] = pd.to_datetime(df["ts"], utc=True)

    df["hour_utc"] = df["ts"].dt.hour
    df["hour_ist"] = (df["hour_utc"] + 5) % 24  # IST offset approx
    df["dow"] = df["ts"].dt.dayofweek
    df["month"] = df["ts"].dt.month
    df["is_weekend"] = (df["dow"] >= 5).astype(int)
    # Solar angle proxy: sin/cos of hour
    df["hour_sin"] = np.sin(2 * np.pi * df["hour_ist"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour_ist"] / 24)
    df["dow_sin"]  = np.sin(2 * np.pi * df["dow"] / 7)
    df["dow_cos"]  = np.cos(2 * np.pi * df["dow"] / 7)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    df["region_enc"] = df["region"].map(REGION_MAP).fillna(2)

    # Lagged CI (if available - for inference we'll use twin medians)
    for lag in [1, 2, 3, 6, 12, 24]:
        df[f"ci_lag_{lag}"] = df.groupby("region")["ci_g_per_kwh"].shift(lag)

    # Renewable share
    df["renewable_share"] = df.get("renewable_share", pd.Series(0.3, index=df.index))

    feature_cols = [
        "hour_sin", "hour_cos", "dow_sin", "dow_cos", "month_sin", "month_cos",
        "is_weekend", "region_enc", "renewable_share",
        "ci_lag_1", "ci_lag_2", "ci_lag_3", "ci_lag_6", "ci_lag_12", "ci_lag_24",
    ]
    return df.dropna(subset=feature_cols), feature_cols


# ── 3. Train ──────────────────────────────────────────────────────────────────

def train(df: pd.DataFrame):
    import joblib
    import lightgbm as lgb
    from sklearn.metrics import mean_absolute_error

    df, feature_cols = build_features(df)
    df = df.sort_values("ts").reset_index(drop=True)

    # 80/20 temporal split
    split = int(len(df) * 0.8)
    train_df, test_df = df.iloc[:split], df.iloc[split:]

    X_train = train_df[feature_cols]
    y_train = train_df["ci_g_per_kwh"]
    X_test  = test_df[feature_cols]
    y_test  = test_df["ci_g_per_kwh"]

    models_dir = settings.models_dir
    models_dir.mkdir(parents=True, exist_ok=True)

    models: dict = {}
    metrics: dict = {}

    for q_name, alpha in [("q10", 0.1), ("q50", 0.5), ("q90", 0.9)]:
        print(f"Training {q_name} (alpha={alpha}) …")
        model = lgb.LGBMRegressor(
            objective="quantile",
            alpha=alpha,
            n_estimators=300,
            learning_rate=0.05,
            max_depth=6,
            num_leaves=31,
            min_child_samples=20,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)])
        preds = model.predict(X_test)
        mae = mean_absolute_error(y_test, preds)
        print(f"  MAE: {mae:.2f} g/kWh")
        metrics[f"{q_name}_mae_g_kwh"] = round(float(mae), 3)
        models[q_name] = model
        joblib.dump(model, models_dir / f"ci_{q_name}.joblib")

    # Per-region, per-horizon calibration
    calibration: dict = {}
    for region in ["NR", "WR", "SR", "ER", "NER"]:
        sub = test_df[test_df["region"] == region]
        if sub.empty:
            continue
        calibration[region] = {}
        for bucket, cond in [("1-6", sub.index < 6), ("7-24", (sub.index >= 6) & (sub.index < 24)), ("25-48", sub.index >= 24)]:
            calibration[region][bucket] = {"q10_adj": 0.0, "q50_adj": 0.0, "q90_adj": 0.0}

    metrics["model_version"] = "lgbm-v1"
    metrics["trained_at"] = datetime.now(timezone.utc).isoformat()
    metrics["n_train"] = len(train_df)
    metrics["n_test"] = len(test_df)
    metrics["features"] = feature_cols

    with open(models_dir / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    with open(models_dir / "calibration.json", "w") as f:
        json.dump(calibration, f, indent=2)

    print(f"\nAll models saved to {models_dir}")
    print(json.dumps(metrics, indent=2, default=str))
    return metrics


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--skip-generate", action="store_true")
    args = parser.parse_args()

    data_path = settings.raw_dir / "synthetic_history.parquet"
    if args.skip_generate and data_path.exists():
        print(f"Loading existing data from {data_path}")
        df = pd.read_parquet(data_path)
    else:
        df = generate_data(args.days)

    train(df)
