"""
Time-series forecasting utilities for WeatherNow.

Everything here operates on a plain 1-D temperature array, so the methods are
easy to test and reuse outside the DB layer. Provides:

  * sequence windowing
  * LSTM training (configurable input window — default 7 days)
  * Monte-Carlo dropout predictive uncertainty (mean + confidence interval)
  * MAE / RMSE evaluation on held-out data
  * persistence and moving-average baselines, for honest benchmarking
  * a window study comparing input-window lengths
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn

from ml.model import WeatherLSTM


def make_sequences(series, seq_len: int):
    """Turn a 1-D series into (X, y) supervised pairs of shape
    (n, seq_len, 1) and (n, 1)."""
    series = np.asarray(series, dtype=np.float32)
    X, y = [], []
    for i in range(len(series) - seq_len):
        X.append(series[i : i + seq_len])
        y.append(series[i + seq_len])
    X = np.array(X, dtype=np.float32).reshape(-1, seq_len, 1)
    y = np.array(y, dtype=np.float32).reshape(-1, 1)
    return X, y


def _standardize(arr):
    arr = np.asarray(arr, dtype=np.float32)
    mean, std = float(np.mean(arr)), float(np.std(arr))
    std = std if std > 1e-8 else 1.0
    return (arr - mean) / std, mean, std


def train_lstm(series, seq_len: int = 7, epochs: int = 100, hidden_size: int = 64,
               dropout: float = 0.2, lr: float = 0.01, seed: int = 42):
    """Train a WeatherLSTM on a standardized series. Returns (model, stats)."""
    torch.manual_seed(seed)
    norm, mean, std = _standardize(series)
    X, y = make_sequences(norm, seq_len)
    if len(X) == 0:
        raise ValueError("series too short for the chosen seq_len")

    model = WeatherLSTM(hidden_size=hidden_size, dropout=dropout)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    Xt, yt = torch.tensor(X), torch.tensor(y)

    model.train()
    for _ in range(epochs):
        optimizer.zero_grad()
        loss = criterion(model(Xt), yt)
        loss.backward()
        optimizer.step()

    return model, {"mean": mean, "std": std, "seq_len": seq_len}


def _enable_mc_dropout(model):
    """Put the model in eval mode but keep Dropout layers stochastic."""
    model.eval()
    for module in model.modules():
        if isinstance(module, nn.Dropout):
            module.train()


def mc_dropout_predict(model, window, stats, n_samples: int = 50, ci: float = 0.95, seed: int = 0):
    """
    Predict the next value with Monte-Carlo dropout uncertainty.
    Runs `n_samples` stochastic forward passes and returns
    (mean, lower, upper) in the ORIGINAL temperature scale.
    """
    torch.manual_seed(seed)
    mean_, std_, seq_len = stats["mean"], stats["std"], stats["seq_len"]
    w = (np.asarray(window, dtype=np.float32)[-seq_len:] - mean_) / std_
    x = torch.tensor(w, dtype=torch.float32).reshape(1, len(w), 1)

    _enable_mc_dropout(model)
    samples = []
    with torch.no_grad():
        for _ in range(n_samples):
            samples.append(float(model(x).item()))

    samples = np.array(samples) * std_ + mean_  # de-standardize
    z = 1.959963985 if abs(ci - 0.95) < 1e-6 else 1.0  # 95% -> 1.96σ, else 68% -> 1σ
    m, s = float(samples.mean()), float(samples.std())
    return m, m - z * s, m + z * s


def evaluate(model, series, stats):
    """One-step-ahead MAE / RMSE over `series` (original scale)."""
    mean_, std_, seq_len = stats["mean"], stats["std"], stats["seq_len"]
    norm = (np.asarray(series, dtype=np.float32) - mean_) / std_
    X, y = make_sequences(norm, seq_len)
    if len(X) == 0:
        return {"mae": float("nan"), "rmse": float("nan")}

    model.eval()
    with torch.no_grad():
        preds = model(torch.tensor(X)).numpy().reshape(-1)
    preds = preds * std_ + mean_
    actual = y.reshape(-1) * std_ + mean_
    err = preds - actual
    return {"mae": float(np.mean(np.abs(err))), "rmse": float(np.sqrt(np.mean(err ** 2)))}


# ---------- baselines ----------
def persistence_mae(series, seq_len: int = 7):
    """Persistence baseline: predict tomorrow == today."""
    s = np.asarray(series, dtype=np.float32)
    actual, pred = s[seq_len:], s[seq_len - 1 : -1]
    return float(np.mean(np.abs(pred - actual))) if len(actual) else float("nan")


def moving_average_mae(series, seq_len: int = 7, window: int = 3):
    """Moving-average baseline: predict the mean of the last `window` days."""
    s = np.asarray(series, dtype=np.float32)
    actual, pred = [], []
    for i in range(seq_len, len(s)):
        actual.append(s[i])
        pred.append(float(np.mean(s[i - window : i])))
    return float(np.mean(np.abs(np.array(pred) - np.array(actual)))) if actual else float("nan")


def compare_baselines(series, seq_len: int = 7, epochs: int = 100, test_frac: float = 0.2):
    """
    Train on the first part of the series, evaluate on the held-out tail, and
    compare the LSTM against persistence and moving-average baselines by MAE.
    All predicted targets fall in the held-out region (no target leakage).
    """
    s = np.asarray(series, dtype=np.float32)
    n_test = max(seq_len + 1, int(len(s) * test_frac))
    train, test = s[:-n_test], s[-(n_test + seq_len):]
    model, stats = train_lstm(train, seq_len=seq_len, epochs=epochs)

    lstm_mae = evaluate(model, test, stats)["mae"]
    pers = persistence_mae(test, seq_len)
    ma = moving_average_mae(test, seq_len)

    def improvement(base):
        return float((base - lstm_mae) / base * 100) if base and not np.isnan(base) else float("nan")

    return {
        "lstm_mae": lstm_mae,
        "persistence_mae": pers,
        "moving_average_mae": ma,
        "improvement_vs_persistence_pct": improvement(pers),
        "improvement_vs_moving_average_pct": improvement(ma),
    }


def window_study(series, windows=(3, 7, 14), epochs: int = 80, test_frac: float = 0.2):
    """Compare held-out LSTM MAE across input-window lengths."""
    out = {}
    for w in windows:
        try:
            out[w] = compare_baselines(series, seq_len=w, epochs=epochs, test_frac=test_frac)["lstm_mae"]
        except ValueError:
            out[w] = float("nan")
    return out
