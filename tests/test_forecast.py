import numpy as np
from ml.forecast import (
    make_sequences,
    train_lstm,
    mc_dropout_predict,
    evaluate,
    persistence_mae,
    moving_average_mae,
    compare_baselines,
)


def _seasonal_series(n=300, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return 15 + 10 * np.sin(2 * np.pi * t / 30) + rng.normal(0, 1.0, n)


def test_make_sequences_shapes():
    X, y = make_sequences(np.arange(20), seq_len=7)
    assert X.shape == (13, 7, 1)
    assert y.shape == (13, 1)


def test_baselines_compute_positive_mae():
    s = _seasonal_series()
    assert persistence_mae(s, 7) > 0
    assert moving_average_mae(s, 7) > 0


def test_mc_dropout_produces_real_uncertainty():
    s = _seasonal_series()
    model, stats = train_lstm(s, seq_len=7, epochs=30)
    mean, lower, upper = mc_dropout_predict(model, s[-7:], stats, n_samples=40)
    assert lower < mean < upper       # a genuine interval
    assert (upper - lower) > 0         # dropout injects non-zero uncertainty


def test_evaluate_returns_finite_mae():
    s = _seasonal_series()
    model, stats = train_lstm(s, seq_len=7, epochs=30)
    m = evaluate(model, s, stats)
    assert m["mae"] >= 0 and np.isfinite(m["mae"])
    assert m["rmse"] >= m["mae"]       # RMSE >= MAE always


def test_compare_baselines_returns_all_metrics():
    s = _seasonal_series()
    res = compare_baselines(s, seq_len=7, epochs=40)
    for k in [
        "lstm_mae",
        "persistence_mae",
        "moving_average_mae",
        "improvement_vs_persistence_pct",
        "improvement_vs_moving_average_pct",
    ]:
        assert k in res
