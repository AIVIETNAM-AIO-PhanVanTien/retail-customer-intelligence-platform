"""Tests for Bronze ingestion (ACM1-29, ACM1-40)."""

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.etl import bronze_ingest


class TestNormalizeColumns:
    """Unit tests for column normalization."""

    def test_flags_cancellations(self):
        df = pd.DataFrame(
            {
                "Invoice": ["489434", "C489449", "A123"],
                "StockCode": ["85048", "22087", "999"],
                "Description": ["Ball", "Lace", "Adj"],
                "Quantity": ["12", "-12", "1"],
                "InvoiceDate": ["1.12.2009 07:45"] * 3,
                "Price": ["6,95", "2,95", "0,00"],
                "Customer ID": ["13085", "16321", ""],
                "Country": ["United Kingdom", "Australia", "United Kingdom"],
                "_parsed_date": pd.to_datetime(["2009-12-01"] * 3),
            }
        )
        result = bronze_ingest.normalize_columns(df)
        assert result.loc[0, "is_cancellation"] == False  # noqa: E712
        assert result.loc[1, "is_cancellation"] == True  # noqa: E712
        # A-prefix is NOT a cancellation (only C is)
        assert result.loc[2, "is_cancellation"] == False  # noqa: E712

    def test_handles_missing_customer_id(self):
        df = pd.DataFrame(
            {
                "Invoice": ["489434"],
                "StockCode": ["85048"],
                "Description": ["Ball"],
                "Quantity": ["12"],
                "InvoiceDate": ["1.12.2009 07:45"],
                "Price": ["6,95"],
                "Customer ID": [""],
                "Country": ["United Kingdom"],
                "_parsed_date": pd.to_datetime(["2009-12-01"]),
            }
        )
        result = bronze_ingest.normalize_columns(df)
        # Missing customer_id should be empty string, not NaN
        assert result.loc[0, "customer_id"] == ""

    def test_snake_case_rename(self):
        df = pd.DataFrame(
            {
                "Invoice": ["489434"],
                "StockCode": ["85048"],
                "Description": ["Ball"],
                "Quantity": ["12"],
                "InvoiceDate": ["1.12.2009 07:45"],
                "Price": ["6,95"],
                "Customer ID": ["13085"],
                "Country": ["United Kingdom"],
                "_parsed_date": pd.to_datetime(["2009-12-01"]),
            }
        )
        result = bronze_ingest.normalize_columns(df)
        for expected in (
            "invoice",
            "stock_code",
            "description",
            "quantity",
            "price",
            "customer_id",
            "country",
        ):
            assert expected in result.columns


class TestIngest:
    """Integration tests for the full ingest flow."""

    def test_ingest_writes_partition_and_log(self, tmp_path, monkeypatch):
        # Write a tiny raw CSV in the expected semicolon format
        raw = tmp_path / "raw.csv"
        raw.write_text(
            "Invoice;StockCode;Description;Quantity;InvoiceDate;Price;Customer ID;Country\n"
            "489434;85048;Ball;12;01.12.2009 07:45;6,95;13085;United Kingdom\n"
            "489435;79323P;Lights;6;02.12.2009 10:00;3,50;13086;France\n",
            encoding="utf-8",
        )
        bronze_dir = tmp_path / "bronze"
        bronze_dir.mkdir()

        monkeypatch.setattr(bronze_ingest, "RAW_PATH", raw)
        monkeypatch.setattr(bronze_ingest, "BRONZE_DIR", bronze_dir)

        bronze_ingest.ingest("2009-12", raw_path=raw)

        # Parquet exists
        pq_path = bronze_dir / "year_month=2009-12" / "data.parquet"
        assert pq_path.exists()

        # Can read it back
        table = pq.read_table(pq_path)
        assert table.num_rows == 2
        assert "is_cancellation" in table.schema.names

        # Log exists
        log_path = bronze_dir / "_ingestion_log.csv"
        assert log_path.exists()

    def test_ingest_is_idempotent(self, tmp_path, monkeypatch):
        bronze_dir = tmp_path / "bronze" / "year_month=2009-12"
        bronze_dir.mkdir(parents=True)
        # Pre-create partition
        (bronze_dir / "data.parquet").write_bytes(b"already_here")

        monkeypatch.setattr(bronze_ingest, "BRONZE_DIR", tmp_path / "bronze")

        # Should not raise and should not overwrite
        bronze_ingest.ingest("2009-12")
        assert (bronze_dir / "data.parquet").read_bytes() == b"already_here"


class TestIngestAllIteration:
    """Verify ingest_all() processes months newest-first."""

    def test_ingest_all_processes_newest_first(self, tmp_path, monkeypatch):
        # Write a raw CSV with rows spanning 3 different months
        raw = tmp_path / "raw.csv"
        raw.write_text(
            "Invoice;StockCode;Description;Quantity;InvoiceDate;Price;Customer ID;Country\n"
            "489434;85048;Ball;12;01.12.2009 07:45;6,95;13085;United Kingdom\n"
            "489435;79323P;Lights;6;15.06.2010 10:00;3,50;13086;France\n"
            "489436;22087;Lace;3;20.01.2011 14:00;2,95;13087;Germany\n",
            encoding="utf-8",
        )
        bronze_dir = tmp_path / "bronze"
        bronze_dir.mkdir()

        monkeypatch.setattr(bronze_ingest, "RAW_PATH", raw)
        monkeypatch.setattr(bronze_ingest, "BRONZE_DIR", bronze_dir)

        processed = bronze_ingest.ingest_all(raw)

        # Must be in descending order (newest first)
        assert processed == sorted(processed, reverse=True), (
            f"ingest_all() did not iterate newest-first: {processed}"
        )
        assert len(processed) == 3
        # First processed should be 2011-01 (newest), last 2009-12 (oldest)
        assert processed[0] == "2011-01"
        assert processed[-1] == "2009-12"
