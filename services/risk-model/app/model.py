"""PyTorch risk-prediction model (Section 7.1).

A small feedforward network over the 12 engineered features mapping to a
continuous 0..1 risk score. Support:

  - train_mlp()          fit on synthetic-but-principled data (see train.py)
  - RiskModel.predict()  forward + gradient-based attribution for top_factors[]
  - load_model()         cached lazy load of artifacts/risk_mlp.pt

The model is served out-of-process (FastAPI microservice); it is never loaded
inside the MCP server process.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

import numpy as np
import torch
import torch.nn as nn

from app.features import FEATURE_NAMES, FEATURE_LABELS, Features

ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
MODEL_PATH = os.path.join(ARTIFACT_DIR, "risk_mlp.pt")
SCALER_PATH = os.path.join(ARTIFACT_DIR, "scaler.json")


class RiskMLP(nn.Module):
    def __init__(self, n_in: int = len(FEATURE_NAMES)) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_in, 16),
            nn.ReLU(),
            nn.Linear(16, 8),
            nn.ReLU(),
            nn.Linear(8, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class RiskModel:
    """Wraps the network + feature normalization + gradient attribution."""

    def __init__(self, path: str = MODEL_PATH) -> None:
        state = torch.load(path, map_location="cpu", weights_only=True)
        self.net = RiskMLP()
        self.net.load_state_dict(state["model"])
        self.net.eval()
        self.mu = np.array(state["mu"], dtype=np.float32)
        self.sigma = np.array(state["sigma"], dtype=np.float32)
        self.path = path

    def _normalize(self, raw: np.ndarray) -> np.ndarray:
        return (raw - self.mu) / (self.sigma + 1e-8)

    def score(self, features: Features) -> float:
        x = torch.tensor(self._normalize(np.array(features.vector(), dtype=np.float32)))
        with torch.no_grad():
            return float(self.net(x.unsqueeze(0)).squeeze(0).item())

    def score_with_factors(self, features: Features) -> tuple[float, list[dict]]:
        """Score 0..1 + the top contributing factors.

        Attribution is gradient-based: impact_i = normalized_x_i * d(score)/dx_i.
        This gives real, per-feature explainability (Section 7.3) instead of a
        black-box number.
        """
        self.net.zero_grad()
        x = torch.tensor(
            self._normalize(np.array(features.vector(), dtype=np.float32)),
            requires_grad=True,
        )
        out = self.net(x.unsqueeze(0))
        score = float(out.item())
        out.backward()
        grad = x.grad.detach().numpy()
        xv = x.detach().numpy()
        impacts = {name: float(g * v) for name, g, v in zip(FEATURE_NAMES, grad, xv)}

        scored = sorted(impacts.items(), key=lambda kv: abs(kv[1]), reverse=True)
        top = []
        for name, impact in scored[:5]:
            if abs(impact) < 1e-4:
                continue
            direction = "increases risk" if impact > 0 else "lowers risk"
            top.append(
                {
                    "feature": name,
                    "label": FEATURE_LABELS.get(name, name),
                    "impact": round(impact, 4),
                    "direction": direction,
                }
            )
        return score, top


@lru_cache(maxsize=1)
def get_model() -> RiskModel:
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"No trained artifact at {MODEL_PATH}. Run `python -m app.train` first."
        )
    return RiskModel()


def normalize_stats(path: str = SCALER_PATH) -> dict:
    with open(path) as fh:
        stats = json.load(fh)
    return stats


if __name__ == "__main__":  # smoke test
    from app.features import compute_features, generate_aggregate_from_seed

    m = get_model()
    f = compute_features(generate_aggregate_from_seed({}))
    s, factors = m.score_with_factors(f)
    print(f"score={s:.3f}")
    for k in factors:
        print(" ", k)