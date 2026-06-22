"""Model QA validation: feature schema, value ranges, and AUC gate."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ml.config import FEATURE_COLUMNS, QA_AUC_GATE

# Features expected in [0, 1] (rates / normalized ratios from safe_divide).
UNIT_INTERVAL_FEATURES: frozenset[str] = frozenset(
    {
        "cancellation_rate",
        "return_quantity_rate",
        "weekend_purchase_ratio",
        "ratio_frequency_90d",
        "velocity_ratio_180d",
        "spending_recency_ratio",
        "velocity_ratio_30d_90d",
        "product_diversity_trend",
    }
)

BINARY_FEATURES: frozenset[str] = frozenset({"is_one_time_buyer", "is_uk"})

NON_NEGATIVE_FEATURES: frozenset[str] = frozenset(
    {
        "recency_days",
        "frequency",
        "monetary",
        "frequency_last_30d",
        "frequency_last_90d",
        "monetary_last_90d",
        "avg_order_value",
        "avg_basket_size",
        "avg_unit_price",
        "total_quantity",
        "unique_products",
        "tenure_days",
        "avg_days_between_orders",
        "std_days_between_orders",
        "days_since_first_purchase",
        "max_single_order_value",
        "min_single_order_value",
        "recency_one_time",
    }
)

CLIPPED_MAX_FEATURES: dict[str, float] = {
    "overdue_ratio": 10.0,
    "purchase_regularity": 5.0,
    "monetary_acceleration": 20.0,
}


@dataclass
class ModelValidationReport:
    """Result of feature + metrics QA checks."""

    issues: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.issues) == 0

    def to_dict(self) -> dict[str, object]:
        return {"issues": self.issues, "passed": self.passed}


def check_feature_schema(
    df: pd.DataFrame,
    feature_columns: list[str] | None = None,
) -> list[str]:
    """Validate feature matrix column set, order, and nullability."""
    expected = feature_columns or FEATURE_COLUMNS
    issues: list[str] = []

    missing = [c for c in expected if c not in df.columns]
    if missing:
        issues.append(f"Missing feature columns: {missing}")

    extra = [c for c in df.columns if c not in expected and c not in ("customer_id", "churn")]
    if extra:
        issues.append(f"Unexpected columns in feature matrix: {extra}")

    present = [c for c in expected if c in df.columns]
    if present and list(present) != list(expected):
        issues.append(
            f"Feature column order mismatch: expected {expected}, got {present}"
        )

    for col in present:
        null_count = int(df[col].isna().sum())
        if null_count:
            issues.append(f"{col} has {null_count} null values")

        if not pd.api.types.is_numeric_dtype(df[col]):
            issues.append(f"{col} must be numeric, got dtype {df[col].dtype}")

    return issues


def check_feature_value_ranges(df: pd.DataFrame) -> list[str]:
    """Validate business value ranges on engineered features."""
    issues: list[str] = []

    for col in BINARY_FEATURES:
        if col not in df.columns:
            continue
        bad = ~df[col].isin([0, 1])
        if bad.any():
            issues.append(
                f"{col}: {int(bad.sum())} rows outside {{0, 1}}"
            )

    for col in NON_NEGATIVE_FEATURES:
        if col not in df.columns:
            continue
        bad = df[col] < 0
        if bad.any():
            issues.append(f"{col}: {int(bad.sum())} rows with negative values")

    for col in UNIT_INTERVAL_FEATURES:
        if col not in df.columns:
            continue
        bad = (df[col] < 0) | (df[col] > 1)
        if bad.any():
            issues.append(
                f"{col}: {int(bad.sum())} rows outside [0, 1]"
            )

    for col, max_val in CLIPPED_MAX_FEATURES.items():
        if col not in df.columns:
            continue
        bad = (df[col] < 0) | (df[col] > max_val)
        if bad.any():
            issues.append(
                f"{col}: {int(bad.sum())} rows outside [0, {max_val}]"
            )

    if "frequency" in df.columns:
        bad = df["frequency"] < 1
        if bad.any():
            issues.append(
                f"frequency: {int(bad.sum())} rows below minimum 1"
            )

    return issues


def check_auc_gate(
    auc_roc: float,
    gate: float = QA_AUC_GATE,
) -> tuple[bool, str]:
    """Return (passed, message) for the model QA AUC threshold."""
    passed = auc_roc >= gate
    status = "PASS" if passed else "FAIL"
    msg = f"AUC gate (>={gate:.2f}): {status} (auc_roc={auc_roc:.4f})"
    return passed, msg


def validate_model_metrics(
    metrics: dict[str, float],
    gate: float = QA_AUC_GATE,
) -> list[str]:
    """Validate evaluation metrics dict includes AUC and passes QA gate."""
    issues: list[str] = []
    if "auc_roc" not in metrics:
        issues.append("metrics missing required key: auc_roc")
        return issues

    passed, msg = check_auc_gate(metrics["auc_roc"], gate=gate)
    if not passed:
        issues.append(msg)
    return issues


def validate_feature_matrix(
    df: pd.DataFrame,
    feature_columns: list[str] | None = None,
) -> ModelValidationReport:
    """Run schema + value-range checks on a feature matrix."""
    report = ModelValidationReport()
    report.issues.extend(check_feature_schema(df, feature_columns))
    if not any("Missing feature" in i for i in report.issues):
        report.issues.extend(check_feature_value_ranges(df))
    return report
