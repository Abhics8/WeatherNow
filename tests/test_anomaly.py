import numpy as np
from ml.anomaly import detect_anomalies


def test_detects_injected_extremes():
    rng = np.random.default_rng(0)
    s = 20 + rng.normal(0, 1.0, 200)
    s[100] = 60.0   # heatwave spike
    s[150] = -30.0  # cold-snap drop
    res = detect_anomalies(s, z_thresh=2.5, window=30)
    assert 100 in res["anomaly_indices"]
    assert 150 in res["anomaly_indices"]
    assert res["count"] >= 2


def test_quiet_series_has_no_anomalies():
    s = np.full(120, 20.0) + np.random.default_rng(1).normal(0, 0.5, 120)
    res = detect_anomalies(s, z_thresh=4.0, window=30)
    assert res["count"] == 0
