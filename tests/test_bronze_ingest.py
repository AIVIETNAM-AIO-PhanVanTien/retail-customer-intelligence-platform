"""Tests for Bronze ingestion."""

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
            }
        )
        result = bronze_ingest.normalize_columns(df)
        assert result.loc[0, "is_cancellation"] == False  # noqa: E712
        assert result.loc[1, "is_cancellation"] == True  # noqa: E712
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
            }
        )
        result = bronze_ingest.normalize_columns(df)
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
            }
        )
        result = bronze_ingest.normalize_columns(df)
        for expected in (
            "invoice", "stock_code", "description", "quantity",
            "price", "customer_id", "country",
        ):
            assert expected in result.columns

    def test_shifts_dates_to_2026(self):
        df = pd.DataFrame(
            {
                "Invoice": ["489434"],
                "StockCode": ["85048"],
                "Description": ["Ball"],
                "Quantity": ["12"],
                "InvoiceDate": ["04.12.2011 13:15"],
                "Price": ["6,95"],
                "Customer ID": ["13085"],
                "Country": ["United Kingdom"],
            }
        )
        result = bronze_ingest.normalize_columns(df)
        # 2011-12-04 + 5302 days = 2026-06-10
        assert result.loc[0, "invoice_date"].year == 2026
        assert result.loc[0, "invoice_date"].month == 6
        assert result.loc[0, "original_invoice_date"].year == 2011

    def test_stock_code_uppercase(self):
        df = pd.DataFrame(
            {
                "Invoice": ["1"],
                "StockCode": ["85049a"],
                "Description": ["Ball"],
                "Quantity": ["1"],
                "InvoiceDate": ["1.12.2009 07:45"],
                "Price": ["1,00"],
                "Customer ID": ["1"],
                "Country": ["UK"],
            }
        )
        result = bronze_ingest.normalize_columns(df)
        assert result.loc[0, "stock_code"] == "85049A"


class TestIngest:
    """Integration tests for the full ingest flow."""

    def test_ingest_writes_partition_and_log(self, tmp_path, monkeypatch):
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

        # Discover shifted months first
        months = bronze_ingest._discover_months(raw)
        assert len(months) == 1
        # Month should be in 2024 (shifted from 2009-12)
        assert months[0].startswith("2024-")

        bronze_ingest.ingest(months[0], raw_path=raw)

        pq_path = bronze_dir / f"year_month={months[0]}" / "data.parquet"
        assert pq_path.exists()

        table = pq.ParquetFile(pq_path).read()
        assert table.num_rows == 2
        assert "is_cancellation" in table.schema.names
        # Verify date is shifted
        dates = table.column("invoice_date").to_pylist()
        assert all(d.year >= 2024 for d in dates)

        log_path = bronze_dir / "_ingestion_log.csv"
        assert log_path.exists()

    def test_ingest_is_idempotent(self, tmp_path, monkeypatch):
        bronze_dir = tmp_path / "bronze" / "year_month=2024-06"
        bronze_dir.mkdir(parents=True)
        (bronze_dir / "data.parquet").write_bytes(b"already_here")

        monkeypatch.setattr(bronze_ingest, "BRONZE_DIR", tmp_path / "bronze")

        bronze_ingest.ingest("2024-06")
        assert (bronze_dir / "data.parquet").read_bytes() == b"already_here"


class TestIngestAllIteration:
    """Verify ingest_all() processes months newest-first."""

    def test_ingest_all_processes_newest_first(self, tmp_path, monkeypatch):
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
