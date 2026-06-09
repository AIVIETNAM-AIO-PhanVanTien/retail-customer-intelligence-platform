"""Tests for Silver transform (ACM1-30, ACM1-40)."""

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.etl import silver_transform


class TestRunCleaning:
    def test_deduplicates_and_computes_line_amount(self, bronze_like_df):
        # Add a duplicate row
        df = pd.concat([bronze_like_df, bronze_like_df.iloc[[0]]], ignore_index=True)
        result = silver_transform.run_cleaning(df)

        # Duplicate removed
        assert len(result) < len(df)

        # line_amount = quantity * price
        for _, row in result.iterrows():
            assert abs(row["line_amount"] - row["quantity"] * row["price"]) < 0.01

    def test_filters_zero_price_zero_quantity_noise(self):
        df = pd.DataFrame(
            {
                "invoice": ["A", "B", "C"],
                "stock_code": ["X", "Y", "Z"],
                "description": ["Good", "Noise", "OK"],
                "quantity": [10.0, 0.0, 5.0],
                "invoice_date": pd.to_datetime(["2024-01-01"] * 3),
                "price": [2.0, 0.0, 3.0],
                "customer_id": ["1", "2", "3"],
                "country": ["UK", "UK", "UK"],
                "is_cancellation": [False, False, False],
            }
        )
        result = silver_transform.run_cleaning(df)
        assert len(result) == 2  # noise row dropped

    def test_replaces_empty_description(self):
        df = pd.DataFrame(
            {
                "invoice": ["A"],
                "stock_code": ["X"],
                "description": ["  "],
                "quantity": [1.0],
                "invoice_date": pd.to_datetime(["2024-01-01"]),
                "price": [1.0],
                "customer_id": ["1"],
                "country": ["UK"],
                "is_cancellation": [False],
            }
        )
        result = silver_transform.run_cleaning(df)
        assert result.loc[0, "description"] == "UNKNOWN"


class TestRunDateShift:
    def test_adds_derived_columns(self, bronze_like_df):
        result = silver_transform.run_date_shift(bronze_like_df)
        for col in (
            "original_invoice_date",
            "invoice_year",
            "invoice_month",
            "invoice_day",
            "invoice_quarter",
            "invoice_day_of_week",
            "invoice_week",
            "year_month",
        ):
            assert col in result.columns

    def test_shifts_dates_forward(self, bronze_like_df):
        result = silver_transform.run_date_shift(bronze_like_df)
        # Shifted date must be > original
        assert (result["invoice_date"] > result["original_invoice_date"]).all()

    def test_preserves_original_date(self, bronze_like_df):
        original = bronze_like_df["invoice_date"].copy()
        result = silver_transform.run_date_shift(bronze_like_df)
        assert (result["original_invoice_date"] == original).all()


class TestWriteSilver:
    def test_writes_partition_and_quality_report(self, tmp_path, monkeypatch, bronze_like_df):
        monkeypatch.setattr(silver_transform, "SILVER_DIR", tmp_path)

        cleaned = silver_transform.run_cleaning(bronze_like_df)
        shifted = silver_transform.run_date_shift(cleaned)
        _, report = silver_transform.run_quality_check(shifted, "2009-12")

        silver_transform.write_silver_partition(shifted, "2009-12")
        silver_transform.write_quality_report(report, "2009-12")

        # Partition parquet
        pq_path = tmp_path / "year_month=2009-12" / "data_silver.parquet"
        assert pq_path.exists()
        table = pq.ParquetFile(pq_path).read()
        assert table.num_rows == len(shifted)

        # Quality report JSON
        qr_path = tmp_path / "year_month=2009-12" / "quality_report.json"
        assert qr_path.exists()
        with open(qr_path) as f:
            qr = json.load(f)
        assert qr["year_month"] == "2009-12"

        # Cumulative log
        log_path = tmp_path / "_quality_log.jsonl"
        assert log_path.exists()


class TestProcess:
    def test_is_idempotent(self, tmp_path, monkeypatch):
        part_dir = tmp_path / "year_month=2009-12"
        part_dir.mkdir(parents=True)
        (part_dir / "data_silver.parquet").write_bytes(b"already")

        monkeypatch.setattr(silver_transform, "SILVER_DIR", tmp_path)
        monkeypatch.setattr(silver_transform, "BRONZE_DIR", tmp_path)

        # process() should skip without error
        silver_transform.process("2009-12")


class TestWriteSilverDataConsistency:
    """Verify Silver partition data matches the date-shift contract."""

    def test_year_month_column_matches_shifted_date(self, tmp_path, monkeypatch, bronze_like_df):
        """After date-shift, the year_month column inside the Parquet should
        reflect the shifted date, NOT the original Bronze partition key."""
        monkeypatch.setattr(silver_transform, "SILVER_DIR", tmp_path)

        cleaned = silver_transform.run_cleaning(bronze_like_df)
        shifted = silver_transform.run_date_shift(cleaned)

        # The year_month column should equal the formatted shifted invoice_date
        expected_ym = shifted["invoice_date"].dt.strftime("%Y-%m").astype(str)
        assert (shifted["year_month"] == expected_ym).all()

        # Write and read back to verify Parquet roundtrip
        silver_transform.write_silver_partition(shifted, "2009-12")
        pq_path = tmp_path / "year_month=2009-12" / "data_silver.parquet"
        table = pq.ParquetFile(pq_path).read()
        read_back_ym = table.column("year_month").to_pylist()
        assert read_back_ym == expected_ym.tolist()


class TestProcessAllIteration:
    """Verify process_all() iterates newest month first."""

    def test_processes_newest_first(self, tmp_path, monkeypatch):
        bronze_dir = tmp_path / "bronze"
        silver_dir = tmp_path / "silver"

        # Create 3 Bronze partitions (only directories needed for discovery)
        for ym in ("2009-12", "2010-06", "2011-01"):
            p = bronze_dir / f"year_month={ym}"
            p.mkdir(parents=True)
            # Write a minimal parquet so load_bronze() can read it
            import pyarrow as pa
            import pyarrow.parquet as pqw

            tiny = pa.table({"x": [1]})
            pqw.write_table(tiny, p / "data.parquet")

        # Pre-create Silver partitions for 2 of 3 months (simulate partial run)
        (silver_dir / "year_month=2010-06").mkdir(parents=True)
        (silver_dir / "year_month=2010-06" / "data_silver.parquet").write_bytes(b"done")

        monkeypatch.setattr(silver_transform, "BRONZE_DIR", bronze_dir)
        monkeypatch.setattr(silver_transform, "SILVER_DIR", silver_dir)

        # Monkey-patch process() to capture call order without running full pipeline
        called_order: list[str] = []

        def _fake_process(ym: str) -> None:
            called_order.append(ym)

        monkeypatch.setattr(silver_transform, "process", _fake_process)

        silver_transform.process_all()

        # Should be called in descending year_month order
        assert called_order == sorted(called_order, reverse=True), (
            f"process_all() did not iterate newest-first: {called_order}"
        )
