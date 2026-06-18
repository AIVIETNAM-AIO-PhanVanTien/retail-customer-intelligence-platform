"""Tests for Gold layer: star schema + RFM mart."""

import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.etl import gold_build
from src.utils.layer_validation import (
    check_fact_cancellation_measure_rules,
    check_rfm_reconciliation,
    valid_purchase_rows,
    _rfm_eligible_customer_count,
    _rfm_eligible_revenue,
)


def _build_fact_from_silver(df: pd.DataFrame) -> pd.DataFrame:
    """Build fact_transactions at full Silver grain."""
    dim_date = gold_build.build_dim_date(df)
    dim_customer = gold_build.build_dim_customer(df)
    dim_product = gold_build.build_dim_product(df)
    dim_country = gold_build.build_dim_country(df)
    return gold_build.build_fact_transactions(
        df, dim_customer, dim_product, dim_country, dim_date
    )


def _silver_multi_customer_df() -> pd.DataFrame:
    """5-row Silver-like DataFrame with 3 customers across 4 months."""
    return pd.DataFrame(
        {
            "invoice": ["A1", "A2", "A3", "A4", "A5"],
            "stock_code": ["P1", "P2", "P3", "P4", "P5"],
            "description": ["X", "Y", "Z", "W", "V"],
            "quantity": [10.0, 5.0, 2.0, 8.0, 20.0],
            "price": [5.0, 10.0, 3.0, 7.0, 2.0],
            "customer_id": ["C1", "C1", "C2", "C2", "C3"],
            "country": ["UK", "UK", "FR", "FR", "UK"],
            "is_cancellation": [False, False, False, False, False],
            "line_amount": [50.0, 50.0, 6.0, 56.0, 40.0],
            "invoice_date": pd.to_datetime(
                ["2026-06-01", "2026-05-15", "2026-04-01", "2026-03-01", "2026-05-30"]
            ),
            "original_invoice_date": pd.to_datetime(
                ["2011-12-02", "2011-11-15", "2011-10-02", "2011-09-01", "2011-11-30"]
            ),
            "invoice_year": [2026, 2026, 2026, 2026, 2026],
            "invoice_month": [6, 5, 4, 3, 5],
            "invoice_day": [1, 15, 1, 1, 30],
            "invoice_quarter": [2, 2, 2, 1, 2],
            "invoice_day_of_week": [0, 4, 2, 6, 5],
            "invoice_week": [23, 20, 14, 9, 22],
            "year_month": ["2026-06", "2026-05", "2026-04", "2026-03", "2026-05"],
        }
    )


class TestDimensions:
    def test_dim_date_has_all_calendar_columns(self, silver_like_df):
        dim = gold_build.build_dim_date(silver_like_df)
        for col in ("date_sk", "date", "year", "month", "week", "day_of_week", "quarter"):
            assert col in dim.columns
        assert dim["date_sk"].is_unique

    def test_dim_customer_has_unknown_row(self, silver_like_df):
        dim = gold_build.build_dim_customer(silver_like_df)
        unknown = dim[dim["customer_sk"] == 0]
        assert len(unknown) == 1
        assert unknown.iloc[0]["customer_id"] == ""
        assert unknown.iloc[0]["segment"] == "Unknown"
        assert dim["customer_sk"].is_unique

    def test_dim_product_has_unique_sk(self, silver_like_df):
        dim = gold_build.build_dim_product(silver_like_df)
        assert "product_sk" in dim.columns
        assert dim["product_sk"].is_unique
        assert dim["stock_code"].is_unique

    def test_dim_country_has_unique_sk(self, silver_like_df):
        dim = gold_build.build_dim_country(silver_like_df)
        assert "country_sk" in dim.columns
        assert dim["country_sk"].is_unique


class TestFact:
    def test_joins_surrogate_keys(self, silver_like_df):
        fact = _build_fact_from_silver(silver_like_df)

        assert "transaction_sk" in fact.columns
        assert "is_cancellation" in fact.columns
        assert fact["transaction_sk"].is_unique
        assert fact["customer_sk"].notna().all()
        assert fact["product_sk"].notna().all()
        assert fact["country_sk"].notna().all()
        assert fact["date_sk"].notna().all()
        assert check_fact_cancellation_measure_rules(fact) == []

    def test_empty_customer_id_maps_to_unknown_sk(self):
        df = pd.DataFrame(
            {
                "invoice": ["A1", "A2"],
                "stock_code": ["P1", "P2"],
                "description": ["X", "Y"],
                "quantity": [10.0, 5.0],
                "price": [5.0, 3.0],
                "customer_id": ["", "C1"],
                "country": ["UK", "FR"],
                "is_cancellation": [False, False],
                "line_amount": [50.0, 15.0],
                "invoice_date": pd.to_datetime(["2026-06-01", "2026-06-02"]),
            }
        )
        fact = _build_fact_from_silver(df)

        assert fact.iloc[0]["customer_sk"] == 0
        assert fact.iloc[1]["customer_sk"] == 1

    def test_fact_matches_silver_grain(self, silver_like_df):
        """Gold fact is 1:1 with Silver (purchases + cancellations)."""
        fact = _build_fact_from_silver(silver_like_df)
        assert len(fact) == len(silver_like_df)
        pd.testing.assert_series_equal(
            fact["quantity"].reset_index(drop=True),
            silver_like_df["quantity"].reset_index(drop=True),
            check_names=False,
        )
        pd.testing.assert_series_equal(
            fact["line_amount"].reset_index(drop=True),
            silver_like_df["line_amount"].reset_index(drop=True),
            check_names=False,
        )

    def test_fact_includes_cancellations_with_negative_measures(self):
        """Cancellation rows stay in fact with negative qty/amount."""
        df = pd.DataFrame(
            {
                "invoice": ["A1", "C2", "A3"],
                "stock_code": ["P1", "P2", "P3"],
                "description": ["X", "Y", "Z"],
                "quantity": [10.0, -2.0, 5.0],
                "price": [5.0, 3.0, 4.0],
                "customer_id": ["C1", "C1", "C2"],
                "country": ["UK", "UK", "FR"],
                "is_cancellation": [False, True, False],
                "line_amount": [50.0, -6.0, 20.0],
                "invoice_date": pd.to_datetime(
                    ["2026-06-01", "2026-06-02", "2026-06-03"]
                ),
            }
        )
        fact = _build_fact_from_silver(df)

        assert len(fact) == 3
        cancel_row = fact[fact["is_cancellation"]]
        assert len(cancel_row) == 1
        assert cancel_row.iloc[0]["quantity"] == -2.0
        assert cancel_row.iloc[0]["line_amount"] == -6.0
        assert check_fact_cancellation_measure_rules(fact) == []

    def test_cancellation_measure_rules_flag_cancel_with_positive_qty(self):
        fact = pd.DataFrame(
            {
                "transaction_sk": [1],
                "customer_sk": [1],
                "product_sk": [1],
                "country_sk": [1],
                "date_sk": [1],
                "quantity": [5.0],
                "price": [4.0],
                "line_amount": [20.0],
                "is_cancellation": [True],
            }
        )
        issues = check_fact_cancellation_measure_rules(fact)
        assert any("cancellation rows with quantity >= 0" in i for i in issues)

    def test_cancellation_measure_rules_flag_non_cancellation_negatives(self):
        fact = pd.DataFrame(
            {
                "transaction_sk": [1, 2],
                "customer_sk": [1, 2],
                "product_sk": [1, 2],
                "country_sk": [1, 1],
                "date_sk": [1, 2],
                "quantity": [10.0, -1.0],
                "price": [5.0, 4.0],
                "line_amount": [50.0, 10.0],
                "is_cancellation": [False, False],
            }
        )
        issues = check_fact_cancellation_measure_rules(fact)
        assert any("quantity < 0 but is_cancellation = false" in i for i in issues)

        fact2 = fact.copy()
        fact2["quantity"] = [10.0, 2.0]
        fact2["line_amount"] = [50.0, -8.0]
        issues2 = check_fact_cancellation_measure_rules(fact2)
        assert any("line_amount < 0" in i for i in issues2)


class TestRFM:
    def test_scores_in_range_and_segment_valid(self):
        df = _silver_multi_customer_df()
        rfm = gold_build.build_rfm_mart(df)

        for col in ("r_score", "f_score", "m_score"):
            assert rfm[col].between(1, 5).all(), f"{col} out of range"

        for seg in rfm["segment"]:
            assert seg in gold_build.VALID_SEGMENTS

        assert (rfm["recency_days"] >= 0).all()
        assert (rfm["frequency"] >= 1).all()
        assert (rfm["monetary"] > 0).all()

    def test_excludes_cancellations(self):
        df = pd.DataFrame(
            {
                "invoice": ["A1", "C2", "A3", "A4", "A5"],
                "stock_code": ["P1", "P2", "P3", "P4", "P5"],
                "description": ["X", "Y", "Z", "W", "V"],
                "quantity": [10.0, -5.0, 6.0, 3.0, 8.0],
                "price": [5.0, 3.0, 4.0, 2.0, 1.0],
                "customer_id": ["C1", "C1", "C1", "C2", "C2"],
                "country": ["UK", "UK", "UK", "FR", "FR"],
                "is_cancellation": [False, True, False, False, False],
                "line_amount": [50.0, -15.0, 24.0, 6.0, 8.0],
                "invoice_date": pd.to_datetime(
                    ["2026-06-01", "2026-06-02", "2026-06-03", "2026-05-01", "2026-05-02"]
                ),
            }
        )
        rfm = gold_build.build_rfm_mart(df)
        c1 = rfm[rfm["customer_id"] == "C1"]
        assert c1["frequency"].values[0] == 2
        assert c1["monetary"].values[0] == pytest.approx(74.0)

    def test_segment_enrichment(self, silver_like_df):
        dim = gold_build.build_dim_customer(silver_like_df)
        df = _silver_multi_customer_df()
        rfm = gold_build.build_rfm_mart(df)
        enriched = gold_build.enrich_dim_customer_with_segment(dim, rfm)

        rfm_ids = set(rfm["customer_id"])
        for _, row in enriched[enriched["customer_id"].isin(rfm_ids)].iterrows():
            assert row["segment"] != "UNKNOWN"

    def test_rfm_monetary_reconciles_eligible_silver(self):
        df = _silver_multi_customer_df()
        rfm = gold_build.build_rfm_mart(df)
        assert check_rfm_reconciliation(rfm, df, source_layer="silver") == []
        assert float(rfm["monetary"].sum()) == pytest.approx(_rfm_eligible_revenue(df))

    def test_rfm_segment_counts_sum_to_customer_base(self):
        df = _silver_multi_customer_df()
        rfm = gold_build.build_rfm_mart(df)
        eligible_count = _rfm_eligible_customer_count(df)
        assert len(rfm) == eligible_count
        assert int(rfm["segment"].value_counts().sum()) == len(rfm)
        assert rfm["customer_id"].is_unique

    def test_rfm_uses_valid_purchase_rows_only(self):
        df = pd.DataFrame(
            {
                "invoice": ["A1", "C2", "A3"],
                "stock_code": ["P1", "P2", "P3"],
                "description": ["X", "Y", "Z"],
                "quantity": [10.0, -2.0, 5.0],
                "price": [5.0, 3.0, 4.0],
                "customer_id": ["C1", "C1", "C2"],
                "country": ["UK", "UK", "FR"],
                "is_cancellation": [False, True, False],
                "line_amount": [50.0, -6.0, 20.0],
                "invoice_date": pd.to_datetime(
                    ["2026-06-01", "2026-06-02", "2026-06-03"]
                ),
            }
        )
        rfm = gold_build.build_rfm_mart(df)
        assert len(rfm) == valid_purchase_rows(df)["customer_id"].nunique()


class TestEndToEndPipeline:
    def test_build_skips_when_gold_already_exists(self, tmp_path, monkeypatch):
        from src.etl import bronze_ingest, silver_transform, gold_build as gb

        raw = tmp_path / "raw.csv"
        raw.write_text(
            "Invoice;StockCode;Description;Quantity;InvoiceDate;Price;Customer ID;Country\n"
            "489434;85048;Ball;12;01.12.2009 07:45;6,95;13085;United Kingdom\n"
            "489435;79323P;Lights;6;02.12.2009 10:00;3,50;13086;France\n",
            encoding="utf-8",
        )
        bronze_dir = tmp_path / "bronze"
        silver_dir = tmp_path / "silver"
        gold_dir = tmp_path / "gold"
        bronze_dir.mkdir()
        silver_dir.mkdir()
        gold_dir.mkdir()

        monkeypatch.setattr(bronze_ingest, "RAW_PATH", raw)
        monkeypatch.setattr(bronze_ingest, "BRONZE_DIR", bronze_dir)
        bronze_ingest.ingest_all(raw)

        monkeypatch.setattr(silver_transform, "BRONZE_DIR", bronze_dir)
        monkeypatch.setattr(silver_transform, "SILVER_DIR", silver_dir)
        silver_transform.process_all()

        monkeypatch.setattr(gb, "SILVER_DIR", silver_dir)
        monkeypatch.setattr(gb, "GOLD_DIR", gold_dir)
        gb.build()

        fact_path = gold_dir / "fact_transactions" / "fact_transactions.parquet"
        first_bytes = fact_path.read_bytes()
        first_rows = pq.ParquetFile(fact_path).read().num_rows

        gb.build()
        assert fact_path.read_bytes() == first_bytes
        assert pq.ParquetFile(fact_path).read().num_rows == first_rows

    def test_bronze_silver_gold_roundtrip(self, tmp_path, monkeypatch):
        import json

        from src.etl import bronze_ingest, silver_transform, gold_build as gb

        raw = tmp_path / "raw.csv"
        raw.write_text(
            "Invoice;StockCode;Description;Quantity;InvoiceDate;Price;Customer ID;Country\n"
            "489434;85048;Ball;12;01.12.2009 07:45;6,95;13085;United Kingdom\n"
            "489435;79323P;Lights;6;02.12.2009 10:00;3,50;13086;France\n"
            "489436;22087;Lace;3;03.12.2009 11:00;2,95;13087;Germany\n"
            "489437;85023A;Egg;8;04.12.2009 09:00;1,65;13088;Spain\n"
            "489438;21733;Felt;5;05.12.2009 14:00;4,50;13089;Italy\n"
            "C48949;79123;Return;-2;06.12.2009 16:00;3,00;13090;Portugal\n"
            "489500;85048;Ball;10;15.06.2010 08:00;6,95;13085;United Kingdom\n"
            "489501;22087;Lace;4;16.06.2010 09:00;2,95;13086;France\n"
            "489502;79323P;Lights;7;17.06.2010 10:00;3,50;13087;Germany\n"
            "489503;85023A;Egg;2;01.10.2010 11:00;1,65;13088;Spain\n"
            "489504;21733;Felt;6;02.10.2010 12:00;4,50;13089;Italy\n",
            encoding="utf-8",
        )
        bronze_dir = tmp_path / "bronze"
        silver_dir = tmp_path / "silver"
        gold_dir = tmp_path / "gold"
        bronze_dir.mkdir()
        silver_dir.mkdir()
        gold_dir.mkdir()

        monkeypatch.setattr(bronze_ingest, "RAW_PATH", raw)
        monkeypatch.setattr(bronze_ingest, "BRONZE_DIR", bronze_dir)
        processed_months = bronze_ingest.ingest_all(raw)
        assert len(processed_months) >= 2

        monkeypatch.setattr(silver_transform, "BRONZE_DIR", bronze_dir)
        monkeypatch.setattr(silver_transform, "SILVER_DIR", silver_dir)
        silver_months = silver_transform.process_all()
        assert len(silver_months) >= 2

        monkeypatch.setattr(gb, "SILVER_DIR", silver_dir)
        monkeypatch.setattr(gb, "GOLD_DIR", gold_dir)
        gb.build()

        for table_name in (
            "dim_date",
            "dim_customer",
            "dim_product",
            "dim_country",
            "fact_transactions",
            "mart_rfm",
        ):
            path = gold_dir / table_name / f"{table_name}.parquet"
            assert path.exists(), f"Gold table {table_name} not found"
            assert pq.ParquetFile(path).read().num_rows > 0

        fact = pq.ParquetFile(
            gold_dir / "fact_transactions" / "fact_transactions.parquet"
        ).read().to_pandas()
        assert fact["customer_sk"].notna().all()

        silver = pd.concat(
            [pq.ParquetFile(p).read().to_pandas() for p in silver_parts],
            ignore_index=True,
        ) if (silver_parts := sorted(silver_dir.glob("year_month=*/data_silver.parquet"))) else pd.DataFrame()

        assert len(fact) == len(silver)
        assert check_fact_cancellation_measure_rules(fact) == []
        cancel_rows = fact[fact["is_cancellation"]]
        assert len(cancel_rows) >= 1
        assert (cancel_rows["quantity"] < 0).any()

        log_path = gold_dir / "_build_log.json"
        with open(log_path) as f:
            log = json.load(f)
        assert log["silver_rows"] > 0
        assert log["fact_transactions_rows"] == log["silver_rows"]
        assert log["fact_null_customer_sk"] == 0
