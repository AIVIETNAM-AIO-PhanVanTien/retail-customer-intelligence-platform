"""Tests for ML model QA: feature schema, value ranges, AUC gate."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.config import FEATURE_COLUMNS, QA_AUC_GATE
from ml.features import build_customer_features
from ml.validation import (
    check_auc_gate,
    check_feature_schema,
    check_feature_value_ranges,
    validate_feature_matrix,
    validate_model_metrics,
)


def _valid_feature_row() -> dict[str, float]:
    """Single customer row satisfying all range rules."""
    return {
        "recency_days": 30.0,
        "frequency": 5.0,
        "monetary": 250.0,
        "frequency_last_30d": 2.0,
        "frequency_last_90d": 4.0,
        "monetary_last_90d": 180.0,
        "avg_order_value": 50.0,
        "avg_basket_size": 10.0,
        "avg_unit_price": 5.0,
        "total_quantity": 50.0,
        "unique_products": 8.0,
        "tenure_days": 120.0,
        "avg_days_between_orders": 30.0,
        "std_days_between_orders": 5.0,
        "days_since_first_purchase": 150.0,
        "is_one_time_buyer": 0.0,
        "cancellation_rate": 0.1,
        "return_quantity_rate": 0.0,
        "weekend_purchase_ratio": 0.25,
        "monetary_trend": -2.5,
        "max_single_order_value": 80.0,
        "min_single_order_value": 20.0,
        "ratio_frequency_90d": 0.8,
        "velocity_ratio_180d": 0.9,
        "spending_recency_ratio": 0.72,
        "velocity_ratio_30d_90d": 0.5,
        "overdue_ratio": 1.0,
        "purchase_regularity": 0.2,
        "recency_one_time": 0.0,
        "product_diversity_trend": 0.6,
        "monetary_acceleration": 1.1,
        "is_uk": 1.0,
    }


@pytest.fixture
def valid_features_df() -> pd.DataFrame:
    return pd.DataFrame([_valid_feature_row()])[FEATURE_COLUMNS]


class TestFeatureSchema:
    def test_passes_valid_matrix(self, valid_features_df):
        assert check_feature_schema(valid_features_df) == []

    def test_detects_missing_columns(self, valid_features_df):
        df = valid_features_df.drop(columns=["monetary"])
        issues = check_feature_schema(df)
        assert any("Missing feature columns" in i for i in issues)
        assert "monetary" in issues[0]

    def test_detects_unexpected_columns(self, valid_features_df):
        df = valid_features_df.copy()
        df["leakage_flag"] = 1
        issues = check_feature_schema(df)
        assert any("Unexpected columns" in i for i in issues)

    def test_detects_nulls(self, valid_features_df):
        df = valid_features_df.copy()
        df.loc[0, "frequency"] = np.nan
        issues = check_feature_schema(df)
        assert any("frequency" in i and "null" in i for i in issues)

    def test_detects_non_numeric_dtype(self, valid_features_df):
        df = valid_features_df.copy()
        df["recency_days"] = df["recency_days"].astype(object)
        issues = check_feature_schema(df)
        assert any("recency_days" in i and "numeric" in i for i in issues)


class TestFeatureValueRanges:
    def test_passes_valid_row(self, valid_features_df):
        assert check_feature_value_ranges(valid_features_df) == []

    def test_detects_binary_violation(self, valid_features_df):
        df = valid_features_df.copy()
        df.loc[0, "is_uk"] = 2
        issues = check_feature_value_ranges(df)
        assert any("is_uk" in i for i in issues)

    def test_detects_negative_count_feature(self, valid_features_df):
        df = valid_features_df.copy()
        df.loc[0, "frequency"] = -1
        issues = check_feature_value_ranges(df)
        assert any("frequency" in i for i in issues)

    def test_detects_unit_interval_violation(self, valid_features_df):
        df = valid_features_df.copy()
        df.loc[0, "cancellation_rate"] = 1.5
        issues = check_feature_value_ranges(df)
        assert any("cancellation_rate" in i for i in issues)

    def test_detects_clipped_max_violation(self, valid_features_df):
        df = valid_features_df.copy()
        df.loc[0, "overdue_ratio"] = 11.0
        issues = check_feature_value_ranges(df)
        assert any("overdue_ratio" in i for i in issues)


class TestAucGate:
    def test_passes_at_threshold(self):
        passed, msg = check_auc_gate(QA_AUC_GATE)
        assert passed
        assert "PASS" in msg

    def test_passes_above_threshold(self):
        passed, _ = check_auc_gate(0.85)
        assert passed

    def test_fails_below_threshold(self):
        passed, msg = check_auc_gate(0.79)
        assert not passed
        assert "FAIL" in msg

    def test_validate_model_metrics_passes(self):
        assert validate_model_metrics({"auc_roc": 0.82}) == []

    def test_validate_model_metrics_fails(self):
        issues = validate_model_metrics({"auc_roc": 0.75})
        assert len(issues) == 1
        assert "AUC gate" in issues[0]

    def test_validate_model_metrics_missing_auc(self):
        issues = validate_model_metrics({"accuracy": 0.9})
        assert any("auc_roc" in i for i in issues)


class TestValidateFeatureMatrix:
    def test_combined_report_passes(self, valid_features_df):
        report = validate_feature_matrix(valid_features_df)
        assert report.passed
        assert report.issues == []

    def test_combined_report_collects_schema_and_range_issues(self):
        df = pd.DataFrame([_valid_feature_row()])
        df = df.drop(columns=["monetary", "is_uk"])
        df["is_uk"] = 3
        report = validate_feature_matrix(df)
        assert not report.passed
        assert any("Missing feature" in i for i in report.issues)


class TestFeatureBuilderValidation:
    """Engineered features from Silver should satisfy QA rules."""

    def test_build_customer_features_passes_validation(self):
        obs_end = pd.Timestamp("2024-06-30")
        transactions = pd.DataFrame(
            {
                "invoice": ["A1", "A2", "A3", "B1", "B2"],
                "stock_code": ["P1", "P2", "P3", "P1", "P2"],
                "quantity": [10.0, 5.0, 8.0, 12.0, 6.0],
                "price": [5.0, 4.0, 3.0, 2.0, 3.0],
                "line_amount": [50.0, 20.0, 24.0, 24.0, 18.0],
                "customer_id": ["C1", "C1", "C1", "C2", "C2"],
                "country": ["United Kingdom", "United Kingdom", "United Kingdom", "France", "France"],
                "is_cancellation": [False, False, False, False, False],
                "invoice_date": pd.to_datetime(
                    [
                        "2024-05-01",
                        "2024-05-15",
                        "2024-06-10",
                        "2024-06-01",
                        "2024-06-20",
                    ]
                ),
            }
        )
        features = build_customer_features(transactions, obs_end)
        report = validate_feature_matrix(features)
        assert report.passed, report.issues

        assert list(features.columns[:1]) == ["customer_id"]
        assert list(features.columns[1:]) == FEATURE_COLUMNS
