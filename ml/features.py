"""Feature engineering for the LightGBM forecaster."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add hour, month, day of week, etc."""
    # Ensure ts is in IST for feature extraction
    try:
        from app.core.time import to_ist
        df["ts_ist"] = df["ts"].apply(to_ist)
    except ImportError:
        # Fallback if running purely inside ML context without backend imports
        import pytz
        ist = pytz.timezone("Asia/Kolkata")
        df["ts_ist"] = df["ts"].dt.tz_convert(ist)

    df["hour"] = df["ts_ist"].dt.hour
    df["month"] = df["ts_ist"].dt.month
    df["dayofweek"] = df["ts_ist"].dt.dayofweek
    df["is_weekend"] = (df["dayofweek"] >= 5).astype(int)
    
    # Cyclical features
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    
    return df


def add_lag_features(df: pd.DataFrame, target_col: str = "ci_g_per_kwh") -> pd.DataFrame:
    """Add lag features (T-1, T-24, T-48, T-168)."""
    # Assuming dataframe is sorted by TS and is continuous per region
    df = df.sort_values(by=["region", "ts"]).reset_index(drop=True)
    
    for lag in [1, 2, 24, 48, 168]:
        df[f"{target_col}_lag_{lag}"] = df.groupby("region")[target_col].shift(lag)
        
    # Rolling means
    df[f"{target_col}_roll_24"] = df.groupby("region")[target_col].rolling(window=24, min_periods=1).mean().reset_index(level=0, drop=True)
    
    # Fill NAs with mean of the region
    for col in df.columns:
        if "lag" in col or "roll" in col:
            df[col] = df.groupby("region")[col].transform(lambda x: x.fillna(x.mean()))
            
    return df


def build_training_features(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Build complete feature set for training."""
    df = raw_df.copy()
    df = add_time_features(df)
    df = add_lag_features(df, "ci_g_per_kwh")
    
    # Demand and weather are considered 'known' at inference time via weather forecasts
    # For synthetic data, we use the generated values
    feature_cols = [
        "hour", "month", "dayofweek", "is_weekend",
        "hour_sin", "hour_cos", "month_sin", "month_cos",
        "ci_g_per_kwh_lag_1", "ci_g_per_kwh_lag_2", "ci_g_per_kwh_lag_24", 
        "ci_g_per_kwh_lag_48", "ci_g_per_kwh_lag_168", "ci_g_per_kwh_roll_24",
        "demand_mw", "share_solar", "share_wind" # Treat as pseudo-forecasts
    ]
    
    # Region embedding (One-Hot)
    regions = pd.get_dummies(df["region"], prefix="reg")
    for col in regions.columns:
        feature_cols.append(col)
    df = pd.concat([df, regions], axis=1)
    
    return df, feature_cols


def build_inference_features(
    region: str, 
    issued_at: datetime, 
    horizon_hours: int
) -> pd.DataFrame:
    """Build feature matrix for prediction at runtime.
    
    In a real system, this would query recent history and weather forecasts.
    Here we build a simplified matrix based on the region and time.
    """
    from app.services.carbon_sources.twin import TwinSource
    
    # 1. Get recent history to build lags (T-1 to T-168)
    twin = TwinSource()
    hist_start = issued_at - timedelta(hours=168)
    hist_df = twin.history(region, hist_start, issued_at)
    
    # 2. Get forecast horizon weather/demand (from twin for simplicity)
    future_start = issued_at
    future_end = issued_at + timedelta(hours=horizon_hours)
    future_df = twin.history(region, future_start, future_end)
    
    # 3. Combine and feature engineer
    combined = pd.concat([hist_df, future_df]).reset_index(drop=True)
    combined = add_time_features(combined)
    combined = add_lag_features(combined, "ci_g_per_kwh")
    
    # Region one-hot
    for r in ["NR", "WR", "SR", "ER", "NER"]:
        combined[f"reg_{r}"] = 1 if r == region else 0
        
    # Filter to only the inference horizon
    inference_df = combined[combined["ts"] >= issued_at].copy()
    
    # Return just the feature columns (hardcoded list from training)
    feature_cols = [
        "hour", "month", "dayofweek", "is_weekend",
        "hour_sin", "hour_cos", "month_sin", "month_cos",
        "ci_g_per_kwh_lag_1", "ci_g_per_kwh_lag_2", "ci_g_per_kwh_lag_24", 
        "ci_g_per_kwh_lag_48", "ci_g_per_kwh_lag_168", "ci_g_per_kwh_roll_24",
        "demand_mw", "share_solar", "share_wind"
    ]
    for r in ["NR", "WR", "SR", "ER", "NER"]:
        feature_cols.append(f"reg_{r}")
        
    return inference_df[feature_cols]
