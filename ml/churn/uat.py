"""UAT helpers: scoring output validation, churn_flag metrics, retention export."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

SCORING_COLUMNS: tuple[str, ...] = (
    "customer_id",
    "churn_probability",
    "churn_flag",
    "risk_tier",
)

RETENTION_EXPORT_COLUMNS: tuple[str, ...] = (
    "customer_id",
    "segment",
    "churn_probability",
    "risk_tier",
    "recency_days",
    "frequency",
    "monetary",
)

RISK_TIER_LABELS: frozenset[str] = frozenset({"High", "Medium", "Low"})
DEFAULT_HIGH_THRESHOLD = 0.7
DEFAULT_MEDIUM_THRESHOLD = 0.4


@dataclass
class UATReport:
    """Result of churn scoring / retention UAT checks."""

    issues: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return len(self.issues) == 0

    def to_dict(self) -> dict[str, object]:
        return {"issues": self.issues, "metrics": self.metrics, "passed": self.passed}


def assign_risk_tier(
    probabilities: pd.Series,
    *,
    high_threshold: float = DEFAULT_HIGH_THRESHOLD,
    medium_threshold: float = DEFAULT_MEDIUM_THRESHOLD,
) -> pd.Series:
    """Map churn probabilities to High / Medium / Low tiers."""
    return pd.Series(
        np.select(
            [
                probabilities >= high_threshold,
                probabilities >= medium_threshold,
            ],
            ["High", "Medium"],
            default="Low",
        ),
        index=probabilities.index,
    )


def apply_scoring_columns(
    customers_df: pd.DataFrame,
    threshold: float,
    *,
    probability_col: str = "churn_probability",
) -> pd.DataFrame:
    """Derive churn_flag and risk_tier from stored probabilities (serving UAT)."""
    if probability_col not in customers_df.columns:
        raise ValueError(f"Missing probability column: {probability_col}")

    scoring_df = pd.DataFrame(
        {
            "customer_id": customers_df["customer_id"].values,
            "churn_probability": customers_df[probability_col].values,
        }
    )
    scoring_df["churn_flag"] = (
        scoring_df["churn_probability"] >= threshold
    ).astype(int)
    scoring_df["risk_tier"] = assign_risk_tier(scoring_df["churn_probability"])
    return scoring_df


def validate_predictions(
    scoring_df: pd.DataFrame,
    threshold: float,
    *,
    expected_row_count: int | None = None,
) -> list[str]:
    """Validate batch scoring output schema and business rules."""
    issues: list[str] = []

    missing = [c for c in SCORING_COLUMNS if c not in scoring_df.columns]
    if missing:
        issues.append(f"Missing scoring columns: {missing}")
        return issues

    if scoring_df["customer_id"].isna().any():
        issues.append("customer_id contains null values")

    dupes = int(scoring_df["customer_id"].duplicated().sum())
    if dupes:
        issues.append(f"customer_id has {dupes} duplicate rows")

    if expected_row_count is not None and len(scoring_df) != expected_row_count:
        issues.append(
            f"Row count mismatch: expected {expected_row_count}, got {len(scoring_df)}"
        )

    proba = scoring_df["churn_probability"]
    if proba.isna().any():
        issues.append("churn_probability contains null values")
    if (proba < 0).any() or (proba > 1).any():
        issues.append("churn_probability outside [0, 1]")

    flag = scoring_df["churn_flag"]
    if not flag.isin([0, 1]).all():
        issues.append("churn_flag must be 0 or 1")

    expected_flag = (proba >= threshold).astype(int)
    mismatches = int((flag != expected_flag).sum())
    if mismatches:
        issues.append(
            f"churn_flag inconsistent with threshold {threshold:.4f}: "
            f"{mismatches} rows"
        )

    tiers = scoring_df["risk_tier"]
    invalid_tiers = set(tiers.unique()) - RISK_TIER_LABELS
    if invalid_tiers:
        issues.append(f"Invalid risk_tier values: {sorted(invalid_tiers)}")

    expected_tiers = assign_risk_tier(proba)
    tier_mismatches = int((tiers != expected_tiers).sum())
    if tier_mismatches:
        issues.append(f"risk_tier inconsistent with probability: {tier_mismatches} rows")

    return issues


def churn_flag_metrics(
    y_true: pd.Series | np.ndarray,
    churn_flag: pd.Series | np.ndarray,
) -> dict[str, float]:
    """Classification metrics for churn_flag vs ground-truth labels."""
    y_true = np.asarray(y_true, dtype=int)
    churn_flag = np.asarray(churn_flag, dtype=int)

    return {
        "accuracy": float(accuracy_score(y_true, churn_flag)),
        "precision_churn": float(
            precision_score(y_true, churn_flag, pos_label=1, zero_division=0)
        ),
        "recall_churn": float(
            recall_score(y_true, churn_flag, pos_label=1, zero_division=0)
        ),
        "f1_churn": float(
            f1_score(y_true, churn_flag, pos_label=1, zero_division=0)
        ),
        "true_positives": float(confusion_matrix(y_true, churn_flag)[1, 1]),
        "false_positives": float(confusion_matrix(y_true, churn_flag)[0, 1]),
        "true_negatives": float(confusion_matrix(y_true, churn_flag)[0, 0]),
        "false_negatives": float(confusion_matrix(y_true, churn_flag)[1, 0]),
    }


def build_retention_list(
    customers_df: pd.DataFrame,
    *,
    threshold: float,
    risk_tiers: list[str] | None = None,
    segments: list[str] | None = None,
    min_monetary: float = 0.0,
    high_threshold: float = DEFAULT_HIGH_THRESHOLD,
    medium_threshold: float = DEFAULT_MEDIUM_THRESHOLD,
) -> pd.DataFrame:
    """Filter scored customers into a retention targeting list (Streamlit parity)."""
    scored = customers_df.copy()
    if "churn_probability" not in scored.columns:
        raise ValueError("customers_df must include churn_probability")

    if "churn_flag" not in scored.columns:
        scored["churn_flag"] = (scored["churn_probability"] >= threshold).astype(int)
    if "risk_tier" not in scored.columns:
        scored["risk_tier"] = assign_risk_tier(
            scored["churn_probability"],
            high_threshold=high_threshold,
            medium_threshold=medium_threshold,
        )

    tiers = risk_tiers if risk_tiers is not None else ["High"]
    view = scored[scored["risk_tier"].isin(tiers)]
    if segments:
        if "segment" not in view.columns:
            raise ValueError("segment filter requested but column is missing")
        view = view[view["segment"].isin(segments)]
    if "monetary" not in view.columns:
        raise ValueError("customers_df must include monetary for min_monetary filter")
    view = view[view["monetary"] >= min_monetary]
    return view.sort_values("churn_probability", ascending=False).reset_index(drop=True)


def export_retention_csv(
    retention_df: pd.DataFrame,
    columns: tuple[str, ...] | None = None,
) -> str:
    """Serialize the retention list to CSV (Streamlit download parity)."""
    cols = columns or RETENTION_EXPORT_COLUMNS
    missing = [c for c in cols if c not in retention_df.columns]
    if missing:
        raise ValueError(f"Retention export missing columns: {missing}")
    return retention_df[list(cols)].to_csv(index=False)


def validate_retention_export(
    retention_df: pd.DataFrame,
    *,
    source_df: pd.DataFrame | None = None,
) -> list[str]:
    """Validate retention list shape, columns, and filter consistency."""
    issues: list[str] = []

    missing = [c for c in RETENTION_EXPORT_COLUMNS if c not in retention_df.columns]
    if missing:
        issues.append(f"Retention export missing columns: {missing}")
        return issues

    if retention_df["customer_id"].isna().any():
        issues.append("Retention export has null customer_id")

    if retention_df["customer_id"].duplicated().any():
        issues.append("Retention export has duplicate customer_id")

    proba = retention_df["churn_probability"]
    if (proba < 0).any() or (proba > 1).any():
        issues.append("Retention export churn_probability outside [0, 1]")

    if not retention_df["risk_tier"].isin(RISK_TIER_LABELS).all():
        issues.append("Retention export has invalid risk_tier values")

    if not retention_df["churn_probability"].is_monotonic_decreasing:
        issues.append("Retention export must be sorted by churn_probability desc")

    if source_df is not None:
        extra = set(retention_df["customer_id"]) - set(source_df["customer_id"])
        if extra:
            issues.append(
                f"Retention export contains {len(extra)} customers not in source"
            )

    return issues


def parse_retention_csv(csv_text: str) -> pd.DataFrame:
    """Load a retention CSV export for round-trip UAT checks."""
    return pd.read_csv(StringIO(csv_text))


def validate_scoring_uat(
    scoring_df: pd.DataFrame,
    threshold: float,
    *,
    y_true: pd.Series | None = None,
    expected_row_count: int | None = None,
    min_accuracy: float | None = None,
) -> UATReport:
    """Run scoring UAT checks; optionally evaluate churn_flag accuracy on labels."""
    report = UATReport()
    report.issues.extend(
        validate_predictions(
            scoring_df,
            threshold,
            expected_row_count=expected_row_count,
        )
    )

    if y_true is not None:
        if isinstance(y_true, pd.DataFrame):
            labels = y_true[["customer_id", "churn"]].copy()
        else:
            labels = pd.DataFrame(
                {
                    "customer_id": scoring_df["customer_id"].values,
                    "churn": np.asarray(y_true, dtype=int),
                }
            )
        aligned = scoring_df.merge(labels, on="customer_id", how="inner")
        if len(aligned) != len(scoring_df):
            report.issues.append(
                f"Label join dropped {len(scoring_df) - len(aligned)} scoring rows"
            )
        if len(aligned):
            report.metrics = churn_flag_metrics(aligned["churn"], aligned["churn_flag"])
            if min_accuracy is not None and report.metrics["accuracy"] < min_accuracy:
                report.issues.append(
                    f"churn_flag accuracy {report.metrics['accuracy']:.4f} "
                    f"below minimum {min_accuracy:.4f}"
                )

    return report


def validate_retention_uat(
    customers_df: pd.DataFrame,
    *,
    threshold: float,
    risk_tiers: list[str] | None = None,
    segments: list[str] | None = None,
    min_monetary: float = 0.0,
) -> UATReport:
    """Build retention list, export CSV, and validate round-trip."""
    report = UATReport()
    try:
        retention = build_retention_list(
            customers_df,
            threshold=threshold,
            risk_tiers=risk_tiers,
            segments=segments,
            min_monetary=min_monetary,
        )
    except ValueError as exc:
        report.issues.append(str(exc))
        return report

    report.issues.extend(validate_retention_export(retention, source_df=customers_df))

    try:
        csv_text = export_retention_csv(retention)
        round_trip = parse_retention_csv(csv_text)
    except ValueError as exc:
        report.issues.append(str(exc))
        return report

    if len(round_trip) != len(retention):
        report.issues.append("CSV round-trip row count mismatch")

    report.metrics["retention_list_size"] = float(len(retention))
    report.metrics["revenue_at_stake"] = float(retention["monetary"].sum())
    return report
