import torch
import torch.nn as nn


class WeatherLSTM(nn.Module):
    """
    2-layer LSTM temperature forecaster with dropout.

    The dropout layer is what enables Monte-Carlo dropout uncertainty at
    inference time (see ml/forecast.mc_dropout_predict): keeping dropout active
    across many stochastic forward passes yields a predictive distribution, not
    just a point estimate.
    """

    def __init__(self, input_size=1, hidden_size=64, num_layers=2, output_size=1, dropout=0.2):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.lstm = nn.LSTM(
            input_size,
            hidden_size,
            num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        out, _ = self.lstm(x)              # (batch, seq_len, hidden)
        out = self.dropout(out[:, -1, :])  # last time step + dropout
        return self.fc(out)
