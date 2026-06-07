import os
import numpy as np
import torch
import torch.nn as nn
from sqlalchemy.orm import Session

from services.weather_service import get_history_stats
from ml.model import WeatherLSTM
from ml.forecast import make_sequences, mc_dropout_predict, evaluate

SEQ_LENGTH = 7  # 7-day input window


def train_model(db: Session, city: str, epochs: int = 100):
    records = get_history_stats(db, city, days=365)
    if len(records) < SEQ_LENGTH + 5:
        return None, f"Not enough data to train (need at least {SEQ_LENGTH + 5} records)"

    temps = [r.temp_c for r in records]
    temps.reverse()  # oldest first
    temps = np.array(temps, dtype=np.float32)

    mean_temp, std_temp = float(np.mean(temps)), float(np.std(temps))
    std_temp = std_temp if std_temp > 1e-8 else 1.0
    norm = (temps - mean_temp) / std_temp

    X, y = make_sequences(norm, SEQ_LENGTH)
    Xt, yt = torch.tensor(X), torch.tensor(y)

    model = WeatherLSTM()
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

    model.train()
    for _ in range(epochs):
        optimizer.zero_grad()
        loss = criterion(model(Xt), yt)
        loss.backward()
        optimizer.step()

    os.makedirs("ml/models", exist_ok=True)
    model_path = f"ml/models/{city.lower()}_lstm.pth"
    torch.save(
        {"model_state": model.state_dict(), "mean": mean_temp, "std": std_temp, "seq_len": SEQ_LENGTH},
        model_path,
    )

    stats = {"mean": mean_temp, "std": std_temp, "seq_len": SEQ_LENGTH}
    mae = evaluate(model, temps, stats)["mae"]
    return model_path, f"Training complete. Loss: {loss.item():.4f} | in-sample MAE: {mae:.2f}°C"


def _load(city: str):
    model_path = f"ml/models/{city.lower()}_lstm.pth"
    if not os.path.exists(model_path):
        return None, None
    try:
        ckpt = torch.load(model_path)
        model = WeatherLSTM()
        model.load_state_dict(ckpt["model_state"])
        return model, ckpt
    except Exception:
        return None, None  # stale/incompatible checkpoint -> retrain


def predict_next_day(city: str, recent_temps: list):
    """Point forecast for the next day."""
    model, ckpt = _load(city)
    if model is None:
        return None
    model.eval()
    seq_len = ckpt.get("seq_len", SEQ_LENGTH)
    w = (np.array(recent_temps, dtype=np.float32)[-seq_len:] - ckpt["mean"]) / ckpt["std"]
    x = torch.tensor(w, dtype=torch.float32).reshape(1, len(w), 1)
    with torch.no_grad():
        pred = model(x)
    return float(pred.item()) * ckpt["std"] + ckpt["mean"]


def predict_with_uncertainty(city: str, recent_temps: list, n_samples: int = 50, ci: float = 0.95):
    """Next-day forecast with a Monte-Carlo dropout confidence interval."""
    model, ckpt = _load(city)
    if model is None:
        return None
    stats = {"mean": ckpt["mean"], "std": ckpt["std"], "seq_len": ckpt.get("seq_len", SEQ_LENGTH)}
    mean_pred, lower, upper = mc_dropout_predict(model, recent_temps, stats, n_samples=n_samples, ci=ci)
    return {"prediction": mean_pred, "lower": lower, "upper": upper, "ci": ci}
