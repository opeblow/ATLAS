"""Train the ATLAS risk-prediction MLP (Section 7.1).

Generates a synthetic but *principled* dataset: the target risk score is a
nonlinear function of the engineered features plus noise, so the network must
actually learn a mapping — this is a real trained model, not a hardcoded rule.

Run:  python -m app.train
Writes: artifacts/risk_mlp.pt, artifacts/scaler.json
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

import numpy as np
import torch
import torch.nn as nn

from app.features import FEATURE_NAMES, compute_features, generate_aggregate_from_seed
from app.model import ARTIFACT_DIR, MODEL_PATH, SCALER_PATH, RiskMLP

torch.manual_seed(2026)
np.random.seed(2026)


def true_risk(x: np.ndarray, names: list[str] | None = None) -> np.ndarray:
    """Ground-truth risk function used to synthesize labels.

    Captures the domain intuition the spec describes (spending spikes, thin
    balance margins, subscriptions growing, income instability) as learnable
    structure the MLP has to discover.
    """
    names = names or FEATURE_NAMES
    idx = {n: i for i, n in enumerate(names)}

    balance_cover = x[:, idx["balance_cover_months"]]
    trend = x[:, idx["spend_trend_30d"]]
    recur = x[:, idx["recur_sub_ratio"]]
    prox = x[:, idx["overdraft_proximity"]]
    util = x[:, idx["utilization"]]
    income_ok = x[:, idx["income_stability"]]
    projected = x[:, idx["projected_amount_ratio"]]

    logit = (
        -1.1 * np.log1p(np.maximum(balance_cover, 0.0))       # more cover, safer
        + 2.2 * np.tanh(2.0 * trend)                          # spend spike -> risk
        + 1.6 * np.tanh(3.0 * recur)                          # subs heavy -> risk
        + 3.0 * prox                                          # near overdraft
        + 1.4 * np.tanh(1.5 * (util - 0.7))                   # utilization
        - 0.9 * income_ok
        + 1.8 * np.tanh(2.0 * projected)                      # big purchase probe
        + np.random.normal(0.0, 0.35, size=x.shape[0])        # irreducible noise
    )
    return 1.0 / (1.0 + np.exp(-logit))


def synthesize(n: int = 6000) -> tuple[np.ndarray, np.ndarray]:
    rows = []
    months = 60
    base_monthly = np.random.uniform(150_000, 900_000, n)
    for i in range(n):
        monthly = base_monthly[i]
        balance = np.random.uniform(0.1, 3.5) * monthly
        income = monthly * np.random.uniform(1.0, 1.6)
        if np.random.rand() < 0.18:  # income instability
            income = monthly * np.random.uniform(0.3, 0.6)
        trend = np.clip(np.random.normal(0.05, 0.5), -1.0, 3.0)
        prev21 = max(1.0, monthly * 3.0 * np.clip(1.0 - trend * 0.7, 0.1, 2.5))
        spend_7d = np.clip(monthly * 0.25 * (1.0 + trend), 1000.0, None)
        recur = np.random.uniform(0.02, 0.5) * monthly
        txn = int(np.random.poisson(avg / 7.0)) if (avg := np.random.uniform(3, 60)) else 3
        txn = max(1, txn)

        cats = ["food", "transport", "shopping", "subscriptions", "entertainment", "general"]
        weights = np.random.dirichlet(np.ones(len(cats)))
        cat_spend = {"food": spend_7d * weights[0], "transport": spend_7d * weights[1]}
        for c, w in zip(cats[2:], weights[2:]):
            cat_spend[c] = spend_7d * w

        daily_std = spend_7d / 7.0 * np.random.uniform(0.2, 1.2)
        projected = 0.0 if np.random.rand() < 0.7 else balance * np.random.uniform(0.05, 0.6)

        agg = generate_aggregate_from_seed(
            {
                "balance_ngn": balance,
                "monthly_income_ngn": income,
                "monthly_spend_ngn": monthly,
                "last7d_spend_ngn": spend_7d,
                "prev21d_spend_ngn": prev21,
                "recurring_sub_spend_ngn": recur,
                "txn_count_7d": txn,
                "category_spend": cat_spend,
                "daily_spend_std_ngn": daily_std,
                "income_received_30d": income > monthly * 0.8,
                "projected_amount_ngn": projected,
                # Sweep the seasonal feature across the full year. Leaving it
                # frozen at today's value gave it zero training variance, which
                # collapsed sigma to ~0 and let normalization explode at serve
                # time (every risk score came back 0.00 with no factors).
                "day_of_year": float(np.random.randint(1, 367)),
            }
        )
        rows.append(compute_features(agg).vector())

    X = np.array(rows, dtype=np.float32)
    y = true_risk(X)
    return X, y


def train() -> None:
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    X, y = synthesize()
    mu, sigma = X.mean(axis=0), X.std(axis=0)
    Xn = (X - mu) / (sigma + 1e-8)

    split = int(0.8 * len(X))
    xt, yt = torch.tensor(Xn[:split]), torch.tensor(y[:split], dtype=torch.float32).unsqueeze(1)
    xv, yv = torch.tensor(Xn[split:]), torch.tensor(y[split:], dtype=torch.float32).unsqueeze(1)

    model = RiskMLP()
    opt = torch.optim.Adam(model.parameters(), lr=1e-2)
    loss_fn = nn.MSELoss()

    best_v, best_state = 1e9, None
    for epoch in range(250):
        model.train()
        opt.zero_grad()
        loss = loss_fn(model(xt), yt)
        loss.backward()
        opt.step()

        model.eval()
        with torch.no_grad():
            vloss = loss_fn(model(xv), yv).item()
        if vloss < best_v:
            best_v, best_state = vloss, {k: v.clone() for k, v in model.state_dict().items()}
        if epoch % 50 == 0:
            print(f"epoch {epoch:3d} train {loss.item():.4f} val {vloss:.4f}")

    print(f"best val loss: {best_v:.4f}")
    torch.save({"model": best_state, "mu": mu.tolist(), "sigma": sigma.tolist()}, MODEL_PATH)
    with open(SCALER_PATH, "w") as fh:
        json.dump({"feature_names": FEATURE_NAMES, "mu": mu.tolist(), "sigma": sigma.tolist()}, fh, indent=2)
    print(f"saved -> {MODEL_PATH}")

    # Sanity: correlation between model and ground-truth on the validation fold.
    model.eval()
    with torch.no_grad():
        preds = model(xv).numpy().ravel()
    print(f"validation R={np.corrcoef(preds, yv.numpy().ravel())[0,1]:.3f}")


if __name__ == "__main__":
    train()