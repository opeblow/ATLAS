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
_MIN_SIGMA = 1e-3
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
        # Floor the scale: a feature that was constant during training has
        # sigma ~0, and dividing by it at serve time produces enormous inputs
        # that saturate every ReLU and flatten the score to 0.00.
        self.sigma = np.maximum(np.array(state["sigma"], dtype=np.float32), _MIN_SIGMA)
        self.path = path

    def _normalize(self, raw: np.ndarray) -> np.ndarray:
        return (raw - self.mu) / self.sigma

    def score(self, features: Features) -> float:
        x = torch.tensor(self._normalize(np.array(features.vector(), dtype=np.float32)))
        with torch.no_grad():
            return float(self.net(x.unsqueeze(0)).squeeze(0).item())

    def score_with_factors(self, features: Features) -> tuple[float, list[dict]]:
        """Score 0..1 + the top contributing factors.

        Two distinct quantities, which must not be conflated:

          impact_i    = |d(score)/d(raw_i)| * sigma_i
                        score movement from a one-standard-deviation change
          direction_i = sign(d(score)/d(raw_i))
                        whether raising this feature raises risk

        Two things this fixes. The old code signed the impact by the *normalized*
        value, so any feature sitting below the training mean flipped its
        reported direction ("recurring subscriptions lowers risk" for a user
        whose subscriptions were small). And it used |x_i * g_i| as the
        magnitude, which vanishes for every feature at its training mean — so a
        typical user got one or zero factors instead of a real explanation.

        Scaling the derivative by sigma converts from normalized units back to
        raw-feature units, and because sigma is floored positive the sign of the
        gradient is exactly the sign of d(score)/d(raw).
        """
        self.net.zero_grad()
        x = torch.tensor(
            self._normalize(np.array(features.vector(), dtype=np.float32)),
            requires_grad=True,
        )
        out = self.net(x.unsqueeze(0))
        score = float(out.item())
        out.backward()
        grad = x.grad.detach().numpy().ravel()
        xv = x.detach().numpy().ravel()

        rows = [
            {
                "feature": name,
                "label": FEATURE_LABELS.get(name, name),
                # raw-unit sensitivity: score change per 1 std-dev of this feature
                "impact": round(abs(float(g) * float(s)), 4),
                "direction": "increases risk" if g > 0 else "lowers risk",
            }
            for name, g, s in zip(FEATURE_NAMES, grad, self.sigma)
        ]
        rows.sort(key=lambda r: r["impact"], reverse=True)
        return score, [r for r in rows[:5] if r["impact"] >= 1e-4]


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