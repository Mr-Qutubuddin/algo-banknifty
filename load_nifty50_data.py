"""
Load Nifty 50 1-minute data from Kaggle CSV.
Filters to 09:20–15:15 trading window.
"""
import pandas as pd
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "NIFTY 50_minute.csv"

def load_nifty50_from_csv(
    path: str | Path = None,
    start_date: str = "2025-01-02",
    end_date: str = "2026-04-30",
) -> list[dict]:
    path = Path(path) if path else DATA_FILE
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.rename(columns={"date": "timestamp"})
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Filter date range
    df = df[(df["timestamp"] >= start_date) & (df["timestamp"] <= end_date)]

    # Filter to 09:20–15:15 trading window
    df = df[(df["timestamp"].dt.hour > 9) | (
        (df["timestamp"].dt.hour == 9) & (df["timestamp"].dt.minute >= 20)
    )]
    df = df[(df["timestamp"].dt.hour < 15) | (
        (df["timestamp"].dt.hour == 15) & (df["timestamp"].dt.minute <= 15)
    )]

    return df.to_dict("records")