"""Generate synthetic historical data for ML training.

This script uses the Grid Digital Twin to generate 1 year of historical 
hourly data for all regions, saving it as Parquet files for the ML model.
"""
import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# Fix path to import app modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.core.config import get_settings
from app.services.grid_twin import get_twin

settings = get_settings()


def generate_data(days: int = 365, seed: int = 42):
    """Generate historical grid data using the Twin."""
    twin = get_twin()
    
    # Generate 1 year of data ending yesterday
    end_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=days)
    
    print(f"Generating {days} days of synthetic data from {start_date} to {end_date}...")
    df = twin.generate(start_date, end_date)
    
    # Save raw data
    raw_dir = settings.raw_dir
    os.makedirs(raw_dir, exist_ok=True)
    
    out_file = raw_dir / "synthetic_history.parquet"
    df.to_parquet(out_file, index=False)
    print(f"Saved {len(df)} rows to {out_file}")
    
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    
    generate_data(args.days, args.seed)
