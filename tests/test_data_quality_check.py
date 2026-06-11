"""Tests for TabularDataQuality utility."""

import pandas as pd
import pytest

from src.utils.data_quality_check import TabularDataQuality


class TestRunAllChecks:
    def test_returns_core_quality_sections(self):
        df = pd.DataFrame(
            {
                "invoice": ["A", "B", "B", "D"],
                "stock_code": ["X", "Y", "Y", "Z"],
                "quantity": [10.0, -5.0, 0.0, 2.0],
                "price": [5.0, 3.0, 0.0, 1.0],
                "customer_id": ["1", "2", "", "4"],
                "country": ["UK", "FR", "UK", "UK"],
                "is_cancellation": [False, True, False, False],
                "line_amount": [50.0, -15.0, 0.0, 2.0],
                "invoice_date": pd.to_datetime(
                    ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"]
                ),
            }
        )
        dq = TabularDataQuality(df, key_columns=["invoice", "customer_id"])
        report = dq.run_all_checks()

        for section in ("completeness", "uniqueness", "consistency", "value_ranges", "temporal"):
            assert section in report, f"Missing section: {section}"

    def test_completeness_counts_nulls_and_empty(self):
        df = pd.DataFrame(
            {
                "customer_id": ["1", "", None, "4"],
                "price": [1.0, 2.0, 3.0, 4.0],
            }
        )
        dq = TabularDataQuality(df)
        comp = dq.check_completeness()
        # customer_id has 1 null (None); empty_string_rate counts "" strings
        assert comp["columns"]["customer_id"]["null_count"] == 1
        # empty_string_rate: 1 empty string "" out of 4 rows = 0.25
        # (None becomes NaN, not empty string)
        assert comp["columns"]["customer_id"]["empty_string_rate"] <= 0.5


class TestConsistency:
    def test_detects_cancellation_mismatch(self):
        df = pd.DataFrame(
            {
                "invoice": ["C123", "456"],
                "is_cancellation": [False, True],  # both are wrong
                "quantity": [1.0, 2.0],
            }
        )
        dq = TabularDataQuality(df)
        cons = dq.check_consistency()
        assert cons["cancellation_flag_mismatch"] == 2


class TestValueRanges:
    def test_returns_numeric_stats(self):
        df = pd.DataFrame({"quantity": [10.0, -5.0, 0.0, 100.0]})
        dq = TabularDataQuality(df)
        ranges = dq.check_value_ranges()
        assert ranges["quantity_min"] == -5.0
        assert ranges["quantity_max"] == 100.0
        assert ranges["quantity_zero_count"] == 1


class TestSummaryDf:
    def test_flattens_non_nested_metrics(self):
        df = pd.DataFrame(
            {
                "invoice": ["A", "B"],
                "quantity": [1.0, 2.0],
                "price": [1.0, 2.0],
                "customer_id": ["1", "2"],
                "country": ["UK", "FR"],
                "is_cancellation": [False, True],
                "line_amount": [1.0, 4.0],
                "invoice_date": pd.to_datetime(["2026-01-01", "2026-02-01"]),
            }
        )
        dq = TabularDataQuality(df)
        summary = dq.summary_df()
        assert {"category", "metric", "value"} <= set(summary.columns)
        # Nested dicts like top_duplicates should be excluded
        assert "top_duplicates" not in summary["metric"].values
