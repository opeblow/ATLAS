"""Feature engineering for the ATLAS risk model (Section 7.1).

The finance service computes *aggregates* from the ledger (no raw transaction
rows ever leave it) and posts them here; this module owns the feature math so
the ML model and its explainability stay in exactly one place.
"""

from __future__ import annotations

from datetime import datetime

# Feature vector consumed by the MLP. Keep in sync with FEATURE_LABELS.
FEATURE_NAMES = [
    "balance_cover_months",      # balance / avg monthly spend (higher = safer)
    "spend_7d_norm",             # last-7d spend / monthly-spend scale
    "spend_trend_30d",           # (7d avg - prev 21d avg) / prev avg ; spike detection
    "recur_sub_ratio",           # recurring subscription spend / total spend
    "txn_velocity_7d",           # transaction count last 7d / 7
    "max_category_share",        # largest single-category share of last-7d spend
    "overdraft_proximity",       # how thin margin to the zero bound is
    "spend_volatility",          # daily spend std / daily spend mean
    "income_stability",          # 1.0 if income received in rolling 30d
    "utilization",               # spend / income ratio
    "seasonality_sin",           # day-of-year seasonal signal
    "projected_amount_ratio",    # amount under assessment / balance (0 if none)
]

FEATURE_LABELS = {
    "balance_cover_months": "balance coverage",
    "spend_7d_norm": "recent spend level",
    "spend_trend_30d": "spending trend",
    "recur_sub_ratio": "recurring subscriptions",
    "txn_velocity_7d": "transaction frequency",
    "max_category_share": "category concentration",
    "overdraft_proximity": "overdraft proximity",
    "spend_volatility": "spend volatility",
    "income_stability": "income stability",
    "utilization": "income utilization",
    "seasonality_sin": "seasonal pattern",
    "projected_amount_ratio": "purchase size vs balance",
}


class Features:
    def __init__(self, values: dict[str, float]):
        self.values = values

    def vector(self, names: list[str] | None = None) -> list[float]:
        return [self.values[n] for n in (names or FEATURE_NAMES)]


def compute_features(agg: dict) -> Features:
    """Compute the 12-feature vector from a raw aggregate payload.

    Contract: finance-service sends aggregates (Sections 7.3 & 9), never raw
    transaction rows.
    """
    balance = float(agg.get("balance_ngn", 0.0))
    monthly_income = float(agg.get("monthly_income_ngn", 0.0))
    monthly_spend = float(agg.get("monthly_spend_ngn", 0.0)) or 1.0
    spend_7d = float(agg.get("last7d_spend_ngn", 0.0))
    prev21d_avg = (float(agg.get("prev21d_spend_ngn", 0.0))) / 3.0 or 1.0  # monthly->weekly
    recur_sub = float(agg.get("recurring_sub_spend_ngn", 0.0))
    txn_count_7d = float(agg.get("txn_count_7d", 0))
    category_spend: dict = agg.get("category_spend", {}) or {}
    daily_std = float(agg.get("daily_spend_std_ngn", 0.0))
    daily_mean = spend_7d / 7.0 or 1.0
    income_received = bool(agg.get("income_received_30d", True))
    projected_amount = float(agg.get("projected_amount_ngn") or 0.0)
    # Day-of-year is overridable so training can sweep the full range instead of
    # freezing on the day the dataset was generated.
    day_of_year = float(agg.get("day_of_year") or datetime.now().timetuple().tm_yday)

    total_7d = sum(float(v) for v in category_spend.values()) or spend_7d or 1.0

    # Qualitative risk signals blended into a continuous 0..1 risk score.
    balance_cover = balance / (monthly_spend + 1.0)
    trend = (spend_7d / 7.0 - prev21d_avg) / (abs(prev21d_avg) + 1.0)
    recur_ratio = recur_sub / (monthly_spend * 0.25 + 1.0)
    max_cat_share = max([v / total_7d for v in category_spend.values()] or [0.0])
    overdraft_prox = max(0.0, min(1.0, 1.0 - (balance / (daily_mean * 3.0 + 1.0))))
    volatility = daily_std / (daily_mean + 1.0)
    utilization = min(3.0, (monthly_spend + 1.0) / (monthly_income + 1.0))
    # Smooth 0.5..1.0 over the year (see FEATURE_LABELS).
    seasonal = day_of_year / 366.0
    # Purchase size relative to a stable, non-negative base (income), not
    # balance — balance can legitimately dip negative and would flip the sign.
    projected_ratio = (projected_amount / (monthly_income + 1.0)) if projected_amount > 0 else 0.0

    return Features(
        {
            "balance_cover_months": balance_cover,
            "spend_7d_norm": spend_7d / monthly_spend,
            "spend_trend_30d": trend,
            "recur_sub_ratio": recur_ratio,
            "txn_velocity_7d": txn_count_7d / 7.0,
            "max_category_share": max_cat_share,
            "overdraft_proximity": overdraft_prox,
            "spend_volatility": volatility,
            "income_stability": 1.0 if income_received else 0.0,
            "utilization": utilization,
            "seasonality_sin": 0.5 * (1.0 + seasonal),  # smooth 0.5..1.0
            "projected_amount_ratio": projected_ratio,
        }
    )


def generate_aggregate_from_seed(seed: dict) -> dict:
    """Turn a raw seed dict into defaults-filled aggregates (test convenience)."""
    defaults = {
        "balance_ngn": 250_000,
        "monthly_income_ngn": 400_000,
        "monthly_spend_ngn": 320_000,
        "last7d_spend_ngn": 90_000,
        "prev21d_spend_ngn": 210_000,
        "recurring_sub_spend_ngn": 28_000,
        "txn_count_7d": 18,
        "category_spend": {
            "food": 40_000,
            "transport": 20_000,
            "shopping": 18_000,
            "subscriptions": 12_000,
        },
        "daily_spend_std_ngn": 6_000,
        "income_received_30d": True,
        "projected_amount_ngn": 0,
        "day_of_year": datetime.now().timetuple().tm_yday,
    }
    defaults.update(seed)
    return defaults