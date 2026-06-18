"""Tests for Silver transform."""

import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.etl import silver_transform


class TestRunCleaning:
    def test_deduplicates_and_computes_line_amount(self, bronze_like_df):
        df = pd.concat([bronze_like_df, bronze_like_df.iloc[[0]]], ignore_index=True)
        result = silver_transform.run_cleaning(df)

        assert len(result) < len(df)

        for _, row in result.iterrows():
            assert abs(row["line_amount"] - row["quantity"] * row["price"]) < 0.01

    def test_filters_non_cancellation_zero_price(self):
        """Non-cancellation rows with price <= 0 should be filtered."""
        df = pd.DataFrame(
            {
                "invoice": ["A", "B", "C", "D"],
                "stock_code": ["X", "Y", "Z", "W"],
                "description": ["Good", "Adjust", "OK", "Bad"],
                "quantity": [10.0, -5.0, 5.0, 3.0],
                "invoice_date": pd.to_datetime(["2024-01-01"] * 4),
                "original_invoice_date": pd.to_datetime(["2009-01-01"] * 4),
                "price": [2.0, 0.0, 3.0, -1.0],
                "customer_id": ["1", "2", "3", "4"],
                "country": ["UK", "UK", "UK", "UK"],
                "is_cancellation": [False, False, False, False],
            }
        )
        result = silver_transform.run_cleaning(df)
        # B (price=0) and D (price<0) should be filtered
        assert len(result) == 2
        assert set(result["invoice"].tolist()) == {"A", "C"}

    def test_replaces_empty_description(self):
        df = pd.DataFrame(
            {
                "invoice": ["A"],
                "stock_code": ["X"],
                "description": ["  "],
                "quantity": [1.0],
                "invoice_date": pd.to_datetime(["2024-01-01"]),
                "original_invoice_date": pd.to_datetime(["2009-01-01"]),
                "price": [1.0],
                "customer_id": ["1"],
                "country": ["UK"],
                "is_cancellation": [False],
            }
        )
        result = silver_transform.run_cleaning(df)
        assert result.loc[0, "description"] == "UNKNOWN"


class TestRunDeriveCalendar:
    def test_adds_derived_columns(self, bronze_like_df):
        cleaned = silver_transform.run_cleaning(bronze_like_df)
        result = silver_transform.run_derive_calendar(cleaned)
        for col in (
            "invoice_year", "invoice_month", "invoice_day",
            "invoice_quarter", "invoice_day_of_week", "invoice_week",
            "year_month",
        ):
            assert col in result.columns


class TestWriteSilver:
    def test_writes_partition_and_quality_report(self, tmp_path, monkeypatch, bronze_like_df):
        monkeypatch.setattr(silver_transform, "SILVER_DIR", tmp_path)

        cleaned = silver_transform.run_cleaning(bronze_like_df)
        shifted = silver_transform.run_derive_calendar(cleaned)
        _, report = silver_transform.run_quality_check(shifted, "2024-06")

        silver_transform.write_silver_partition(shifted, "2024-06")
        silver_transform.write_quality_report(report, "2024-06")

        pq_path = tmp_path / "year_month=2024-06" / "data_silver.parquet"
        assert pq_path.exists()
        table = pq.ParquetFile(pq_path).read()
        assert table.num_rows == len(shifted)

        qr_path = tmp_path / "year_month=2024-06" / "quality_report.json"
        assert qr_path.exists()
        with open(qr_path) as f:
            qr = json.load(f)
        assert qr["year_month"] == "2024-06"

        log_path = tmp_path / "_quality_log.jsonl"
        assert log_path.exists()

    def test_year_month_matches_shifted_date(self, tmp_path, monkeypatch, bronze_like_df):
        """year_month column must match the shifted invoice_date."""
        monkeypatch.setattr(silver_transform, "SILVER_DIR", tmp_path)

        cleaned = silver_transform.run_cleaning(bronze_like_df)
        shifted = silver_transform.run_derive_calendar(cleaned)

        expected_ym = shifted["invoice_date"].dt.strftime("%Y-%m").astype(str)
        assert (shifted["year_month"] == expected_ym).all()


class TestProcess:
    def test_is_idempotent(self, tmp_path, monkeypatch):
        part_dir = tmp_path / "year_month=2024-06"
        part_dir.mkdir(parents=True)
        (part_dir / "data_silver.parquet").write_bytes(b"already")

        monkeypatch.setattr(silver_transform, "SILVER_DIR", tmp_path)
        monkeypatch.setattr(silver_transform, "BRONZE_DIR", tmp_path)

        silver_transform.process("2024-06")


class TestProcessAllIteration:
    """Verify process_all() iterates newest month first."""

    def test_processes_newest_first(self, tmp_path, monkeypatch):
        bronze_dir = tmp_path / "bronze"
        silver_dir = tmp_path / "silver"

        for ym in ("2024-06", "2025-01", "2026-05"):
            p = bronze_dir / f"year_month={ym}"
            p.mkdir(parents=True)
            tiny = pa.table({"x": [1]})
            pq.write_table(tiny, p / "data.parquet")

        monkeypatch.setattr(silver_transform, "BRONZE_DIR", bronze_dir)
        monkeypatch.setattr(silver_transform, "SILVER_DIR", silver_dir)

        called_order: list[str] = []

        def _fake_process(ym: str) -> None:
            called_order.append(ym)

        monkeypatch.setattr(silver_transform, "process", _fake_process)

        silver_transform.process_all()

        assert called_order == sorted(called_order, reverse=True), (
            f"process_all() did not iterate newest-first: {called_order}"
        )
