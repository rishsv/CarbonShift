"""Train Quantile Regression LightGBM models for CI forecasting."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import lightgbm as lgb
import pandas as pd
from sklearn.metrics import mean_absolute_error

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.core.config import get_settings
from ml.features import build_training_features

settings = get_settings()


def train_models(data_path: Path):
    """Train p10, p50, and p90 LightGBM models."""
    print(f"Loading data from {data_path}...")
    df = pd.read_parquet(data_path)
    
    # Simple temporal split (last 30 days for eval)
    df = df.sort_values(by="ts").reset_index(drop=True)
    split_date = df["ts"].max() - pd.Timedelta(days=30)
    
    train_df = df[df["ts"] <= split_date].copy()
    test_df = df[df["ts"] > split_date].copy()
    
    # Feature engineering
    print("Building features...")
    X_train, feature_cols = build_training_features(train_df)
    X_test, _ = build_training_features(test_df)
    
    y_train = X_train["ci_g_per_kwh"]
    y_test = X_test["ci_g_per_kwh"]
    
    X_train = X_train[feature_cols]
    X_test = X_test[feature_cols]
    
    # Train 3 models (Quantiles: 0.1, 0.5, 0.9)
    models = {}
    metrics = {}
    
    for q_name, alpha in [("q10", 0.1), ("q50", 0.5), ("q90", 0.9)]:
        print(f"Training {q_name} (alpha={alpha})...")
        model = lgb.LGBMRegressor(
            objective="quantile",
            alpha=alpha,
            n_estimators=200,
            learning_rate=0.05,
            max_depth=6,
            random_state=42,
            n_jobs=-1
        )
        
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            eval_metric="quantile"
        )
        
        models[q_name] = model
        
        # Evaluate
        preds = model.predict(X_test)
        mae = mean_absolute_error(y_test, preds)
        metrics[f"{q_name}_mae"] = mae
        print(f"  {q_name} MAE: {mae:.2f}")

    # Save models
    models_dir = settings.models_dir
    models_dir.mkdir(parents=True, exist_ok=True)
    
    import joblib
    for q_name, model in models.items():
        out_path = models_dir / f"ci_{q_name}.joblib"
        joblib.dump(model, out_path)
        print(f"Saved {q_name} to {out_path}")
        
    metrics["model_version"] = "lgbm-v1"
    with open(models_dir / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, default="data/raw/synthetic_history.parquet")
    args = parser.parse_args()
    
    path = Path(settings.raw_dir.parent.parent / args.data)
    if not path.exists():
        print(f"Data not found at {path}. Run generate_synthetic.py first.")
    else:
        train_models(path)
