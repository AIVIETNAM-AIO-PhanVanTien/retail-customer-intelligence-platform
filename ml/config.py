"""Shared constants and configuration for the ML churn pipeline."""

from __future__ import annotations

from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SILVER_DIR = PROJECT_ROOT / "data" / "silver"
GOLD_DIR = PROJECT_ROOT / "data" / "gold"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"

# Reproducibility
RANDOM_STATE = 42
TEST_SIZE = 0.20

# Temporal windows
EVALUATION_WINDOW_DAYS = 90

# Quality gate
QA_AUC_GATE = 0.80

# MLflow tracking
MLFLOW_TRACKING_URI = "http://127.0.0.1:5001"
MLFLOW_EXPERIMENT_NAME = "churn-prediction"

# Clustering
CLUSTERING_K_RANGE = range(3, 9)
CLUSTERING_ARTIFACT_DIR = ARTIFACT_DIR / "clustering"
MLFLOW_CLUSTERING_EXPERIMENT = "customer-clustering"

# Feature columns (31 features)
FEATURE_COLUMNS: list[str] = [
    # RFM Core
    "recency_days",
    "frequency",
    "monetary",
    # Time-windowed
    "frequency_last_30d",
    "frequency_last_90d",
    "monetary_last_90d",
    # Behavioral
    "avg_order_value",
    "avg_basket_size",
    "avg_unit_price",
    "total_quantity",
    "unique_products",
    # Temporal
    "tenure_days",
    "avg_days_between_orders",
    "std_days_between_orders",
    "days_since_first_purchase",
    "is_one_time_buyer",
    # Engagement
    "cancellation_rate",
    "return_quantity_rate",
    "weekend_purchase_ratio",
    # Monetary pattern
    "monetary_trend",
    "max_single_order_value",
    "min_single_order_value",
    "ratio_frequency_90d",
    # Velocity / Trend Ratios
    "velocity_ratio_180d",
    "spending_recency_ratio",
    "velocity_ratio_30d_90d",
    # Behavioural Signals
    "overdue_ratio",
    "purchase_regularity",
    "recency_one_time",
    "product_diversity_trend",
    "monetary_acceleration",
    # Categorical
    "is_uk",
]

# Skewed features (require log1p transform for linear models)
SKEWED_FEATURES: list[str] = [
    "recency_days",
    "frequency",
    "monetary",
    "avg_order_value",
    "avg_basket_size",
    "avg_unit_price",
    "total_quantity",
    "unique_products",
    "tenure_days",
    "days_since_first_purchase",
    "max_single_order_value",
    "min_single_order_value",
    "frequency_last_30d",
    "frequency_last_90d",
    "monetary_last_90d",
    "overdue_ratio",
    "recency_one_time",
]
