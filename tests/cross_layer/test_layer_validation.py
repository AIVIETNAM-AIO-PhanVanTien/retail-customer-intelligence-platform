"""QA cross-layer validation: Bronze / Silver / Gold (ACM1-40).

Run fast tests (fixture pipeline):
    pytest tests/cross_layer/test_layer_validation.py -v -m "not integration"

Run against real data/ (if pipeline already built):
    pytest tests/cross_layer/test_layer_validation.py -v -m integration
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.utils.layer_validation import (
    check_fact_null_measures,
    check_fact_quantity_rules,
    check_negative_qty_price,
    check_partition_reconciliation,
    check_quantity_cancellation_consistency,
    check_rfm_reconciliation,
    compute_bronze_to_silver_delta,
    compute_layer_metrics,
    expected_staging_partition_counts,
    negative_qty_price_issues,
    read_bronze_partitions,
    read_silver_partitions,
    validate_dbt_layers,
    validate_parquet_layers,
    validate_pipeline_parity,
    valid_purchase_rows,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


def _run_fixture_pipeline(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    """Bronze -> Silver -> Gold on a tiny CSV; return layer dirs."""
    from src.etl import bronze_ingest, gold_build, silver_transform

    raw = tmp_path / "raw.csv"
    raw.write_text(
        "Invoice;StockCode;Description;Quantity;InvoiceDate;Price;Customer ID;Country\n"
        "489434;85048;Ball;12;01.12.2009 07:45;6,95;13085;United Kingdom\n"
        "489434;85048;Ball;12;01.12.2009 07:45;6,95;13085;United Kingdom\n"
        "489435;79323P;Lights;6;02.12.2009 10:00;3,50;13086;France\n"
        "489436;22087;Lace;3;03.12.2009 11:00;2,95;;Germany\n"
        "C48949;79123;Return;-2;06.12.2009 16:00;3,00;13090;Portugal\n"
        "489500;85048;Ball;10;15.06.2010 08:00;6,95;13085;United Kingdom\n"
        "489501;22087;Lace;4;16.06.2010 09:00;2,95;13086;France\n",
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

    monkeypatch.setattr(gold_build, "SILVER_DIR", silver_dir)
    monkeypatch.setattr(gold_build, "GOLD_DIR", gold_dir)
    gold_build.build()

    return bronze_dir, silver_dir, gold_dir


class TestLayerMetrics:
    def test_compute_metrics_detects_duplicates(self):
        df = pd.DataFrame({"invoice": ["A", "A", "B"], "customer_id": ["1", "1", "2"]})
        m = compute_layer_metrics(df, "test")
        assert m.row_count == 3
        assert m.duplicate_rows == 1
        assert m.duplicate_rate > 0

    def test_empty_customer_rate(self):
        df = pd.DataFrame({"customer_id": ["", "1", None]})
        m = compute_layer_metrics(df, "test")
        assert m.empty_customer_rate == pytest.approx(2 / 3, rel=0.01)


class TestBronzeToSilverDelta:
    """S3 / X1: row drop must be explainable (dedup + noise filter)."""

    def test_delta_matches_silver_cleaning_rules(self, bronze_like_df):
        delta = compute_bronze_to_silver_delta(bronze_like_df)
        assert delta.bronze_rows == len(bronze_like_df)
        assert delta.dedup_removed >= 0
        assert delta.noise_removed >= 0
        assert delta.expected_silver_rows == (
            delta.after_dedup - delta.noise_removed
        )

    def test_partition_counts_match_expected_staging(self, bronze_like_df):
        """X5: per-partition expected staging counts reconcile."""
        expected = expected_staging_partition_counts(bronze_like_df)
        assert sum(expected.values()) == compute_bronze_to_silver_delta(
            bronze_like_df
        ).expected_silver_rows


class TestRfmReconciliation:
    """RFM monetary, customer base, and segment distribution checks."""

    def _eligible_silver_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "invoice": ["A1", "A2", "A3", "A4"],
                "stock_code": ["P1", "P2", "P3", "P4"],
                "description": ["X", "Y", "Z", "W"],
                "quantity": [10.0, 5.0, 2.0, 8.0],
                "price": [5.0, 10.0, 3.0, 7.0],
                "customer_id": ["C1", "C1", "C2", "C3"],
                "country": ["UK", "UK", "FR", "UK"],
                "is_cancellation": [False, False, False, False],
                "line_amount": [50.0, 50.0, 6.0, 56.0],
                "invoice_date": pd.to_datetime(
                    ["2026-06-01", "2026-05-15", "2026-04-01", "2026-03-01"]
                ),
            }
        )

    def test_check_rfm_reconciliation_passes(self):
        from src.etl import gold_build

        silver = self._eligible_silver_df()
        rfm = gold_build.build_rfm_mart(silver)
        assert check_rfm_reconciliation(rfm, silver, source_layer="silver") == []

    def test_check_rfm_reconciliation_detects_customer_count_mismatch(self):
        silver = self._eligible_silver_df()
        rfm = pd.DataFrame(
            {
                "customer_id": ["C1", "C2"],
                "monetary": [100.0, 6.0],
                "segment": ["LOYAL", "AT_RISK"],
            }
        )
        issues = check_rfm_reconciliation(rfm, silver, source_layer="silver")
        assert any("eligible customers" in i for i in issues)

    def test_check_rfm_reconciliation_detects_segment_sum_mismatch(self):
        silver = self._eligible_silver_df()
        rfm = pd.DataFrame(
            {
                "customer_id": ["C1", "C2", "C3"],
                "monetary": [100.0, 6.0, 56.0],
                "segment": ["LOYAL", "AT_RISK", None],
            }
        )
        issues = check_rfm_reconciliation(rfm, silver, source_layer="silver")
        assert any("null segment" in i for i in issues)


class TestPartitionReconciliation:
    def test_detects_partition_mismatch(self):
        issues = check_partition_reconciliation(
            {"2024-06": 100, "2024-07": 50},
            {"2024-06": 100, "2024-07": 48},
            "Bronze→Silver",
        )
        assert len(issues) == 1
        assert "2024-07" in issues[0]


class TestQuantityCancellationConsistency:
    def test_bidirectional_rule(self):
        valid = pd.DataFrame(
            {
                "quantity": [10.0, -2.0],
                "is_cancellation": [False, True],
            }
        )
        assert check_quantity_cancellation_consistency(valid, "test") == []

        bad_neg_not_cancel = pd.DataFrame(
            {"quantity": [-1.0], "is_cancellation": [False]}
        )
        issues = check_quantity_cancellation_consistency(bad_neg_not_cancel, "test")
        assert any("quantity < 0 but is_cancellation = false" in i for i in issues)

        bad_cancel_positive = pd.DataFrame(
            {"quantity": [3.0], "is_cancellation": [True]}
        )
        issues2 = check_quantity_cancellation_consistency(bad_cancel_positive, "test")
        assert any("cancellation rows with quantity >= 0" in i for i in issues2)


class TestNegativeQtyPrice:
    """quantity < 0 only on cancellations; price must never be < 0."""

    def test_detects_negative_price(self):
        df = pd.DataFrame(
            {
                "quantity": [1.0, 2.0],
                "price": [-1.0, 3.0],
                "is_cancellation": [False, False],
            }
        )
        check = check_negative_qty_price(df, "test")
        assert check.price_negative_count == 1
        assert negative_qty_price_issues(check)

    def test_detects_negative_qty_on_non_cancellation(self):
        df = pd.DataFrame(
            {
                "quantity": [-5.0, -2.0],
                "price": [1.0, 2.0],
                "is_cancellation": [False, True],
            }
        )
        check = check_negative_qty_price(df, "test")
        assert check.quantity_negative_not_cancellation == 1
        assert check.cancellation_positive_quantity == 0

    def test_passes_valid_cancellation_negative_qty(self):
        df = pd.DataFrame(
            {
                "quantity": [-2.0],
                "price": [3.0],
                "is_cancellation": [True],
            }
        )
        check = check_negative_qty_price(df, "test")
        assert check.passed

    def test_fact_null_measures_detects_nulls(self):
        fact = pd.DataFrame(
            {
                "transaction_sk": [1, 2],
                "customer_sk": [0, 1],
                "product_sk": [1, None],
                "country_sk": [1, 1],
                "date_sk": [1, 1],
                "quantity": [1.0, 2.0],
                "price": [1.0, None],
                "line_amount": [1.0, None],
            }
        )
        issues = check_fact_null_measures(fact)
        assert any("product_sk" in i for i in issues)
        assert any("price" in i for i in issues)

    def test_fact_quantity_rules_detect_mismatch(self):
        fact = pd.DataFrame({"quantity": [10.0, -3.0]})
        silver = pd.DataFrame(
            {"quantity": [10.0, 5.0], "is_cancellation": [False, False]}
        )
        issues = check_fact_quantity_rules(fact, silver)
        assert len(issues) == 1
        assert "quantity !=" in issues[0]

    def test_fact_quantity_rules_passes_when_matched(self):
        fact = pd.DataFrame({"quantity": [10.0, -2.0]})
        silver = pd.DataFrame(
            {"quantity": [10.0, -2.0], "is_cancellation": [False, True]}
        )
        assert check_fact_quantity_rules(fact, silver) == []


class TestParquetLayerValidation:
    """Validate row counts, nulls, duplicates across Bronze -> Silver -> Gold."""

    def test_fixture_pipeline_passes_validation(self, tmp_path, monkeypatch):
        bronze_dir, silver_dir, gold_dir = _run_fixture_pipeline(tmp_path, monkeypatch)

        bronze = read_bronze_partitions(bronze_dir)
        silver = read_silver_partitions(silver_dir)
        report = validate_parquet_layers(bronze_dir, silver_dir, gold_dir)

        assert report.bronze is not None
        assert report.silver is not None
        assert report.passed, report.issues

        assert report.silver.row_count <= report.bronze.row_count
        assert len(bronze) >= len(silver)
        assert report.silver.duplicate_rows == 0
        assert report.bronze_to_silver is not None
        assert report.silver.row_count == report.bronze_to_silver.expected_silver_rows
        assert "line_amount" in silver.columns
        assert report.gold_fact_rows == len(silver)
        assert report.gold_rfm_customers is not None
        assert report.gold_rfm_customers == valid_purchase_rows(silver)["customer_id"].nunique()

    def test_silver_dedup_reduces_row_count(self, tmp_path, monkeypatch):
        bronze_dir, silver_dir, _gold_dir = _run_fixture_pipeline(tmp_path, monkeypatch)
        bronze = read_bronze_partitions(bronze_dir)
        silver = read_silver_partitions(silver_dir)
        assert len(silver) < len(bronze)


@pytest.mark.integration
class TestIntegrationLayerValidation:
    """Run against data/ when full pipeline artifacts exist."""

    @pytest.fixture
    def parquet_layers_exist(self) -> tuple[Path, Path, Path]:
        bronze = DATA_DIR / "bronze"
        silver = DATA_DIR / "silver"
        gold = DATA_DIR / "gold"
        if not list(bronze.glob("year_month=*/data.parquet")):
            pytest.skip("Bronze partitions not found — run bronze_ingest first")
        if not list(silver.glob("year_month=*/data_silver.parquet")):
            pytest.skip("Silver partitions not found — run silver_transform first")
        if not (gold / "fact_transactions" / "fact_transactions.parquet").exists():
            pytest.skip("Gold not found — run gold_build first")
        return bronze, silver, gold

    def test_real_parquet_layers(self, parquet_layers_exist):
        bronze_dir, silver_dir, gold_dir = parquet_layers_exist
        report = validate_parquet_layers(bronze_dir, silver_dir, gold_dir)
        assert report.passed, report.issues

    @pytest.fixture
    def duckdb_exists(self) -> Path:
        db = DATA_DIR / "retail.duckdb"
        if not db.exists():
            pytest.skip("retail.duckdb not found — run dbt run first")
        return db

    def test_real_dbt_layers(self, duckdb_exists):
        bronze_dir = DATA_DIR / "bronze"
        report = validate_dbt_layers(duckdb_exists, bronze_dir=bronze_dir)
        assert report.passed, report.issues

    @pytest.fixture
    def full_pipeline_artifacts(
        self, parquet_layers_exist, duckdb_exists
    ) -> tuple[Path, Path, Path]:
        bronze_dir, silver_dir, gold_dir = parquet_layers_exist
        return gold_dir, duckdb_exists, bronze_dir

    def test_python_dbt_pipeline_parity(self, full_pipeline_artifacts):
        """P1: Python Gold Parquet metrics must match dbt DuckDB marts."""
        gold_dir, duckdb_path, _bronze_dir = full_pipeline_artifacts
        issues = validate_pipeline_parity(gold_dir, duckdb_path)
        assert issues == [], issues


@pytest.mark.integration
class TestDbtQaTests:
    """Run dbt schema + singular tests (P1/P2) when DuckDB artifacts exist."""

    @pytest.fixture
    def duckdb_exists(self) -> Path:
        db = DATA_DIR / "retail.duckdb"
        if not db.exists():
            pytest.skip("retail.duckdb not found — run: cd dbt && dbt run --profiles-dir .")
        return db

    def test_dbt_test_passes(self, duckdb_exists, tmp_path):
        import shutil
        import subprocess

        dbt_dir = REPO_ROOT / "dbt"
        # Copy DB to temp path so dbt test does not fight DataGrip lock on data/
        local_db = tmp_path / "retail.duckdb"
        shutil.copy2(duckdb_exists, local_db)

        profiles = tmp_path / "profiles.yml"
        profiles.write_text(
            f"""retail_duckdb:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: '{local_db}'
      schema: main
""",
            encoding="utf-8",
        )

        result = subprocess.run(
            ["dbt", "test", "--profiles-dir", str(tmp_path)],
            cwd=dbt_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"dbt test failed:\n{result.stdout}\n{result.stderr}"
        )
