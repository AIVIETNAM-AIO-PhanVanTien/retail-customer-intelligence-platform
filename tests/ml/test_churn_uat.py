"""UAT tests: model predictions, churn_flag rules/accuracy, retention export."""

from __future__ import annotations


import numpy as np
import pandas as pd
import pytest

from ml.churn.score import batch_score
from ml.churn.uat import (
    RETENTION_EXPORT_COLUMNS,
    apply_scoring_columns,
    assign_risk_tier,
    build_retention_list,
    churn_flag_metrics,
    export_retention_csv,
    parse_retention_csv,
    validate_predictions,
    validate_retention_export,
    validate_retention_uat,
    validate_scoring_uat,
)
from ml.config import FEATURE_COLUMNS, PROJECT_ROOT
from tests.ml.test_model_validation import _valid_feature_row

APP_DIR = PROJECT_ROOT / "app"
META_PATH = APP_DIR / "model" / "metadata.json"
CUSTOMERS_PATH = APP_DIR / "data" / "customers.parquet"


@pytest.fixture
def threshold() -> float:
    return 0.31


@pytest.fixture
def sample_features_df() -> pd.DataFrame:
    rows = []
    for i, _prob in enumerate([0.1, 0.35, 0.55, 0.75, 0.9]):
        row = _valid_feature_row()
        row["recency_days"] = 10 + i * 20
        rows.append(row)
    df = pd.DataFrame(rows)
    df.insert(0, "customer_id", [f"C{i:03d}" for i in range(len(rows))])
    return df


@pytest.fixture
def mock_model():
    """Model stub that returns fixed probabilities for UAT rule tests."""
    probs = np.array([0.1, 0.35, 0.55, 0.75, 0.9])

    class _ProbaModel:
        def predict_proba(self, X):
            n = len(X)
            p = probs[:n] if n <= len(probs) else np.linspace(0.1, 0.9, n)
            return np.column_stack([1 - p, p])

    return _ProbaModel()


@pytest.fixture
def scored_df(mock_model, sample_features_df, threshold) -> pd.DataFrame:
    return batch_score(mock_model, sample_features_df, threshold)


@pytest.fixture
def customers_for_retention(scored_df: pd.DataFrame) -> pd.DataFrame:
    base = scored_df.copy()
    base["segment"] = ["Champions", "At Risk", "Loyal Customers", "At Risk", "Lost"]
    base["recency_days"] = [10, 120, 30, 200, 400]
    base["frequency"] = [12, 3, 8, 2, 1]
    base["monetary"] = [5000, 800, 1200, 600, 50]
    return base


class TestPredictionValidation:
    def test_valid_batch_score_passes_uat(self, scored_df, threshold, sample_features_df):
        issues = validate_predictions(
            scored_df, threshold, expected_row_count=len(sample_features_df)
        )
        assert issues == []

    def test_detects_missing_columns(self, scored_df, threshold):
        broken = scored_df.drop(columns=["risk_tier"])
        issues = validate_predictions(broken, threshold)
        assert any("Missing scoring columns" in i for i in issues)

    def test_detects_probability_out_of_range(self, scored_df, threshold):
        broken = scored_df.copy()
        broken.loc[0, "churn_probability"] = 1.5
        issues = validate_predictions(broken, threshold)
        assert any("outside [0, 1]" in i for i in issues)

    def test_detects_churn_flag_threshold_mismatch(self, scored_df, threshold):
        broken = scored_df.copy()
        broken.loc[0, "churn_flag"] = 1 - broken.loc[0, "churn_flag"]
        issues = validate_predictions(broken, threshold)
        assert any("churn_flag inconsistent" in i for i in issues)

    def test_detects_risk_tier_mismatch(self, scored_df, threshold):
        broken = scored_df.copy()
        broken.loc[3, "risk_tier"] = "Low"
        issues = validate_predictions(broken, threshold)
        assert any("risk_tier inconsistent" in i for i in issues)

    def test_assign_risk_tier_boundaries(self):
        probs = pd.Series([0.69, 0.7, 0.39, 0.4, 0.1])
        tiers = assign_risk_tier(probs)
        assert tiers.tolist() == ["Medium", "High", "Low", "Medium", "Low"]


class TestChurnFlagAccuracy:
    def test_metrics_on_perfect_predictions(self):
        y_true = pd.Series([0, 1, 0, 1, 1])
        churn_flag = pd.Series([0, 1, 0, 1, 1])
        metrics = churn_flag_metrics(y_true, churn_flag)
        assert metrics["accuracy"] == 1.0
        assert metrics["f1_churn"] == 1.0
        assert metrics["false_positives"] == 0.0
        assert metrics["false_negatives"] == 0.0

    def test_metrics_on_mixed_predictions(self):
        y_true = pd.Series([0, 1, 0, 1, 1])
        churn_flag = pd.Series([0, 1, 0, 0, 1])
        metrics = churn_flag_metrics(y_true, churn_flag)
        assert metrics["accuracy"] == 0.8
        assert metrics["false_negatives"] == 1.0

    def test_validate_scoring_uat_with_labels(self, scored_df, threshold):
        labels = pd.DataFrame(
            {
                "customer_id": scored_df["customer_id"],
                "churn": [0, 1, 1, 1, 1],
            }
        )
        report = validate_scoring_uat(
            scored_df,
            threshold,
            y_true=labels,
            min_accuracy=0.6,
        )
        assert report.passed
        assert "accuracy" in report.metrics
        assert report.metrics["accuracy"] >= 0.6


class TestRetentionExport:
    def test_build_retention_list_default_high_tier(
        self, customers_for_retention, threshold
    ):
        retention = build_retention_list(
            customers_for_retention, threshold=threshold
        )
        assert list(retention["risk_tier"].unique()) == ["High"]
        assert retention["churn_probability"].is_monotonic_decreasing

    def test_build_retention_list_segment_and_monetary_filters(
        self, customers_for_retention, threshold
    ):
        retention = build_retention_list(
            customers_for_retention,
            threshold=threshold,
            risk_tiers=["High"],
            segments=["At Risk"],
            min_monetary=500.0,
        )
        assert len(retention) == 1
        assert retention.iloc[0]["customer_id"] == "C003"
        assert retention.iloc[0]["segment"] == "At Risk"

    def test_export_csv_round_trip(self, customers_for_retention, threshold):
        retention = build_retention_list(
            customers_for_retention, threshold=threshold
        )
        csv_text = export_retention_csv(retention)
        loaded = parse_retention_csv(csv_text)
        assert list(loaded.columns) == list(RETENTION_EXPORT_COLUMNS)
        assert len(loaded) == len(retention)

    def test_validate_retention_export_detects_unsorted(self, customers_for_retention):
        broken = customers_for_retention.sort_values("churn_probability")
        issues = validate_retention_export(broken)
        assert any("sorted" in i for i in issues)

    def test_validate_retention_uat_end_to_end(
        self, customers_for_retention, threshold
    ):
        report = validate_retention_uat(
            customers_for_retention,
            threshold=threshold,
            risk_tiers=["High", "Medium"],
            min_monetary=0.0,
        )
        assert report.passed
        assert report.metrics["retention_list_size"] >= 1.0
        assert report.metrics["revenue_at_stake"] > 0.0


@pytest.mark.integration
class TestServingBundleUAT:
    """UAT against the shipped Streamlit serving bundle (app/)."""

    @pytest.fixture
    def serving_customers(self) -> pd.DataFrame:
        if not CUSTOMERS_PATH.exists() or not META_PATH.exists():
            pytest.skip("Serving bundle not found — run export_serving_app first")
        return pd.read_parquet(CUSTOMERS_PATH)

    @pytest.fixture
    def serving_threshold(self) -> float:
        import json

        with open(META_PATH, encoding="utf-8") as fh:
            return float(json.load(fh).get("optimal_threshold", 0.5))

    def test_serving_parquet_scores_uat(
        self, serving_customers, serving_threshold
    ):
        """Validate exported churn_probability + derived churn_flag/risk_tier."""
        scored = apply_scoring_columns(serving_customers, serving_threshold)
        issues = validate_predictions(
            scored,
            serving_threshold,
            expected_row_count=len(serving_customers),
        )
        assert issues == [], issues

        import json

        with open(META_PATH, encoding="utf-8") as fh:
            meta = json.load(fh)
        expected_rate = meta.get("score_summary", {}).get("pct_churn_flag")
        if expected_rate is not None:
            actual_rate = float(scored["churn_flag"].mean())
            assert abs(actual_rate - expected_rate) < 1e-6

    def test_retention_export_from_serving_customers(
        self, serving_customers, serving_threshold
    ):
        report = validate_retention_uat(
            serving_customers,
            threshold=serving_threshold,
            risk_tiers=["High"],
            min_monetary=0.0,
        )
        assert report.passed, report.issues
        assert report.metrics["retention_list_size"] > 0

    def test_churn_flag_accuracy_on_labeled_holdout(self):
        """Hold-out accuracy with a freshly trained model on Silver features."""
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import Pipeline
        from xgboost import XGBClassifier

        from ml.churn.evaluate import find_optimal_threshold
        from ml.churn.preprocessing import build_tree_preprocessor
        from ml.config import RANDOM_STATE, TEST_SIZE
        from ml.features import build_feature_matrix

        try:
            model_df = build_feature_matrix(mode="train")
        except (FileNotFoundError, OSError):
            pytest.skip("Silver data required for labeled hold-out UAT")

        train_df, test_df = train_test_split(
            model_df,
            test_size=TEST_SIZE,
            stratify=model_df["churn"],
            random_state=RANDOM_STATE,
        )
        pipeline = Pipeline(
            [
                ("preprocess", build_tree_preprocessor()),
                (
                    "model",
                    XGBClassifier(
                        n_estimators=30,
                        max_depth=4,
                        random_state=RANDOM_STATE,
                        eval_metric="logloss",
                    ),
                ),
            ]
        )
        pipeline.fit(train_df[FEATURE_COLUMNS], train_df["churn"].astype(int))
        threshold, _ = find_optimal_threshold(
            pipeline, test_df[FEATURE_COLUMNS], test_df["churn"].astype(int)
        )
        scored = batch_score(pipeline, test_df, threshold)
        labels = test_df[["customer_id", "churn"]]
        report = validate_scoring_uat(
            scored,
            threshold,
            y_true=labels,
            expected_row_count=len(test_df),
            min_accuracy=0.5,
        )
        assert report.passed, report.issues
        assert report.metrics["accuracy"] >= 0.5
