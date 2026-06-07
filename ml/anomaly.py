"""
Statistical anomaly detection for temperature series.

Uses a ROLLING Z-score rather than a single global mean/std, which handles
seasonal drift far better (a 30 °C day is normal in summer, anomalous in
winter). A point is flagged when |z| exceeds the threshold (default 2.5 sigma).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def detect_anomalies(series, z_thresh: float = 2.5, window: int = 30) -> dict:
    s = pd.Series(np.asarray(series, dtype=float)).reset_index(drop=True)
    min_periods = max(2, window // 2)
    roll_mean = s.rolling(window, min_periods=min_periods).mean()
    roll_std = s.rolling(window, min_periods=min_periods).std().replace(0, np.nan)

    z = (s - roll_mean) / roll_std
    mask = (z.abs() > z_thresh).fillna(False)

    return {
        "z_scores": z.to_numpy(),
        "anomaly_indices": s.index[mask].tolist(),
        "anomaly_values": s[mask].tolist(),
        "count": int(mask.sum()),
        "threshold": z_thresh,
        "window": window,
    }
