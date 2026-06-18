"""Cross-layer QA validation for Bronze / Silver / Gold (ACM1-40).

Validates row counts, null rates, duplicates, FK integrity, and RFM
revenue reconciliation across Medallion Parquet layers (Python path)
or DuckDB tables (dbt path).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from src.utils.data_quality_check import TabularDataQuality

KEY_COLUMNS = ["invoice", "stock_code", "customer_id", "country"]
REVENUE_TOLERANCE = 0.001  # 0.1% for RFM vs Silver reconcile
REQUIRED_BRONZE_COLUMNS = [
    "invoice",
    "stock_code",
    "quantity",
    "invoice_date",
    "price",
    "customer_id",
    "country",
    "is_cancellation",
]


@dataclass
class BronzeToSilverDelta:
    """Explainable row-count drop Bronze → Silver/Staging (S3, X1)."""

    bronze_rows: int
    after_dedup: int
    dedup_removed: int
    after_noise_filter: int
    noise_removed: int
    expected_silver_rows: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class NegativeQtyPriceCheck:
    """Business-rule check: negative quantity/price (Silver & Gold)."""

    layer: str
    price_negative_count: int = 0
    quantity_negative_count: int = 0
    quantity_negative_not_cancellation: int = 0
    cancellation_positive_quantity: int = 0

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)

    @property
    def passed(self) -> bool:
        return (
            self.price_negative_count == 0
            and self.quantity_negative_not_cancellation == 0
            and self.cancellation_positive_quantity == 0
        )


def negative_qty_price_messages(
    check: NegativeQtyPriceCheck,
) -> tuple[list[str], list[str]]:
    """Return (hard issues, soft warnings) for qty/price business rules."""
    issues: list[str] = []
    warnings: list[str] = []
    if check.price_negative_count:
        issues.append(
            f"{check.layer}: {check.price_negative_count} rows with price < 0"
        )
    if check.quantity_negative_not_cancellation:
        issues.append(
            f"{check.layer}: {check.quantity_negative_not_cancellation} rows with "
            "quantity < 0 on non-cancellation transactions"
        )
    if check.cancellation_positive_quantity:
        issues.append(
            f"{check.layer}: {check.cancellation_positive_quantity} cancellation "
            "rows with quantity >= 0 (must be negative)"
        )
    return issues, warnings


def negative_qty_price_issues(check: NegativeQtyPriceCheck) -> list[str]:
    """Hard-fail issues only (for unit tests)."""
    issues, _ = negative_qty_price_messages(check)
    return issues


def check_negative_qty_price(
    df: pd.DataFrame,
    layer: str,
    *,
    is_cancellation: pd.Series | None = None,
) -> NegativeQtyPriceCheck:
    """Mirror TabularDataQuality consistency rules for qty/price negatives."""
    result = NegativeQtyPriceCheck(layer=layer)

    if "price" in df.columns:
        result.price_negative_count = int((df["price"] < 0).sum())

    if "quantity" not in df.columns:
        return result

    neg_qty = df["quantity"] < 0
    result.quantity_negative_count = int(neg_qty.sum())

    if is_cancellation is None:
        if "is_cancellation" in df.columns:
            is_cancellation = df["is_cancellation"]
        else:
            return result

    cancel = is_cancellation.astype(bool)
    result.quantity_negative_not_cancellation = int((neg_qty & ~cancel).sum())
    result.cancellation_positive_quantity = int((cancel & ~neg_qty).sum())
    return result


FACT_NOT_NULL_COLUMNS = [
    "transaction_sk",
    "customer_sk",
    "product_sk",
    "country_sk",
    "date_sk",
    "quantity",
    "price",
    "line_amount",
]


def check_fact_null_measures(fact: pd.DataFrame) -> list[str]:
    """No nulls on fact PK, FKs, or measure columns."""
    issues: list[str] = []
    for col in FACT_NOT_NULL_COLUMNS:
        if col not in fact.columns:
            continue
        null_count = int(fact[col].isna().sum())
        if null_count:
            issues.append(
                f"fact_transactions.{col} has {null_count} null values"
            )
    return issues


def check_fact_quantity_rules(
    fact: pd.DataFrame,
    source: pd.DataFrame,
    *,
    source_layer: str = "silver",
) -> list[str]:
    """Gold fact quantity must match upstream layer row-for-row."""
    issues: list[str] = []
    if "quantity" not in fact.columns or "quantity" not in source.columns:
        return issues

    if len(fact) != len(source):
        issues.append(
            f"fact_transactions rows ({len(fact)}) != {source_layer} rows "
            f"({len(source)}) — cannot verify quantity passthrough"
        )
        return issues

    fact_qty = fact["quantity"].reset_index(drop=True)
    source_qty = source["quantity"].reset_index(drop=True)
    mismatched = fact_qty != source_qty
    if mismatched.any():
        issues.append(
            f"fact_transactions.quantity != {source_layer} on "
            f"{int(mismatched.sum())} rows"
        )

    return issues


def valid_purchase_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Rows eligible for RFM / gross sales (mirrors int_transactions__prepared)."""
    if df.empty:
        return df.copy()
    mask = (
        (df["customer_id"].fillna("").astype(str).str.strip() != "")
        & (~df["is_cancellation"].astype(bool))
        & (pd.to_numeric(df["line_amount"], errors="coerce") > 0)
    )
    return df.loc[mask].copy()


def dashboard_eligible_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Rows safe for dashboard fact: quantity and line_amount are not negative."""
    if "quantity" not in df.columns or "line_amount" not in df.columns:
        return df.iloc[0:0].copy()
    mask = (df["quantity"] >= 0) & (df["line_amount"] >= 0)
    return df.loc[mask].copy()


def check_quantity_cancellation_consistency(
    df: pd.DataFrame,
    layer: str,
) -> list[str]:
    """quantity < 0 iff is_cancellation (bidirectional business rule)."""
    if "quantity" not in df.columns or "is_cancellation" not in df.columns:
        return []

    cancel = df["is_cancellation"].astype(bool)
    neg_qty = df["quantity"] < 0
    issues: list[str] = []

    bad_neg = int((neg_qty & ~cancel).sum())
    if bad_neg:
        issues.append(
            f"{layer}: {bad_neg} rows with quantity < 0 but is_cancellation = false"
        )

    bad_cancel = int((cancel & ~neg_qty).sum())
    if bad_cancel:
        issues.append(
            f"{layer}: {bad_cancel} cancellation rows with quantity >= 0 "
            "(must be negative)"
        )
    return issues


def check_fact_cancellation_measure_rules(fact: pd.DataFrame) -> list[str]:
    """Fact measure rules: qty/amount negatives only on cancellation rows."""
    issues: list[str] = []
    if "quantity" not in fact.columns or "line_amount" not in fact.columns:
        return issues

    if "is_cancellation" in fact.columns:
        issues.extend(
            check_quantity_cancellation_consistency(fact, "fact_transactions")
        )
        cancel = fact["is_cancellation"].astype(bool)
        non_cancel = ~cancel
        neg_line_non_cancel = int((non_cancel & (fact["line_amount"] < 0)).sum())
        if neg_line_non_cancel:
            issues.append(
                f"fact_transactions: {neg_line_non_cancel} non-cancellation rows "
                "with line_amount < 0"
            )
        return issues

    # Python path without is_cancellation column: negatives imply cancellations
    neg_qty = int((fact["quantity"] < 0).sum())
    neg_line = int((fact["line_amount"] < 0).sum())
    if neg_qty != neg_line:
        issues.append(
            f"fact_transactions: mismatched negative qty ({neg_qty}) vs "
            f"line_amount ({neg_line}) rows"
        )
    return issues


def check_fact_dashboard_measures(fact: pd.DataFrame) -> list[str]:
    """Fact table rules for dashboard: quantity and line_amount must not be negative."""
    issues: list[str] = []
    if "quantity" in fact.columns:
        neg_qty = int((fact["quantity"] < 0).sum())
        if neg_qty:
            issues.append(
                f"fact_transactions: {neg_qty} rows with quantity < 0"
            )
    if "line_amount" in fact.columns:
        neg_line = int((fact["line_amount"] < 0).sum())
        if neg_line:
            issues.append(
                f"fact_transactions: {neg_line} rows with line_amount < 0"
            )
    return issues


def check_fact_quantity_aggregate(
    fact: pd.DataFrame,
    source: pd.DataFrame,
    *,
    source_layer: str = "staging",
) -> list[str]:
    """Fact vs staging quantity rules without assuming row order (dbt materialized tables)."""
    issues: list[str] = []
    if "quantity" not in fact.columns or "quantity" not in source.columns:
        return issues

    if len(fact) != len(source):
        issues.append(
            f"fact_transactions rows ({len(fact)}) != {source_layer} rows "
            f"({len(source)})"
        )
        return issues

    fact_neg = int((fact["quantity"] < 0).sum())
    source_neg = int((source["quantity"] < 0).sum())
    if fact_neg != source_neg:
        issues.append(
            f"fact negative quantity count ({fact_neg}) != "
            f"{source_layer} ({source_neg})"
        )

    if "is_cancellation" in source.columns:
        bad_neg = int(
            (
                (source["quantity"] < 0)
                & (~source["is_cancellation"].astype(bool))
            ).sum()
        )
        if bad_neg > 0:
            issues.append(
                f"{source_layer}: {bad_neg} rows with quantity < 0 "
                "on non-cancellation transactions"
            )

    return issues


def _try_read_staging_view(con: Any) -> pd.DataFrame | None:
    """Read dbt staging view from DuckDB when Silver parquet path works."""
    for view in ("stg_silver__transactions", "stg_bronze__transactions"):
        try:
            return con.execute(f"SELECT * FROM {view}").df()
        except Exception:
            continue
    return None


def _apply_negative_qty_price_check(
    report: LayerValidationReport,
    check: NegativeQtyPriceCheck,
) -> None:
    issues, warnings = negative_qty_price_messages(check)
    report.issues.extend(issues)
    report.warnings.extend(warnings)


@dataclass
class LayerMetrics:
    """Per-layer summary for QA reporting."""

    layer: str
    row_count: int
    duplicate_rows: int
    duplicate_rate: float
    null_rates: dict[str, float]
    empty_customer_rate: float
    quality: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LayerValidationReport:
    """Full cross-layer validation result."""

    bronze: LayerMetrics | None = None
    silver: LayerMetrics | None = None
    gold_fact_rows: int | None = None
    gold_rfm_customers: int | None = None
    bronze_to_silver: BronzeToSilverDelta | None = None
    silver_qty_price: NegativeQtyPriceCheck | None = None
    gold_fact_qty_price: NegativeQtyPriceCheck | None = None
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.issues) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "bronze": self.bronze.to_dict() if self.bronze else None,
            "silver": self.silver.to_dict() if self.silver else None,
            "gold_fact_rows": self.gold_fact_rows,
            "gold_rfm_customers": self.gold_rfm_customers,
            "bronze_to_silver": (
                self.bronze_to_silver.to_dict() if self.bronze_to_silver else None
            ),
            "silver_qty_price": (
                self.silver_qty_price.to_dict() if self.silver_qty_price else None
            ),
            "gold_fact_qty_price": (
                self.gold_fact_qty_price.to_dict() if self.gold_fact_qty_price else None
            ),
            "issues": self.issues,
            "warnings": self.warnings,
            "passed": self.passed,
        }


def _read_parquet_partitions(paths: list[Path]) -> pd.DataFrame:
    """Read Parquet files one-by-one (avoids cross-partition schema merge issues)."""
    frames: list[pd.DataFrame] = []
    for p in paths:
        df = pq.ParquetFile(p).read().to_pandas()
        if "year_month" in df.columns:
            df["year_month"] = df["year_month"].astype(str)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def read_bronze_partitions(bronze_dir: Path) -> pd.DataFrame:
    """Load all Bronze Parquet partitions into one DataFrame."""
    paths = sorted(bronze_dir.glob("year_month=*/data.parquet"))
    if not paths:
        raise FileNotFoundError(f"No Bronze partitions in {bronze_dir}")
    return _read_parquet_partitions(paths)


def read_silver_partitions(silver_dir: Path) -> pd.DataFrame:
    """Load all Silver Parquet partitions into one DataFrame."""
    paths = sorted(silver_dir.glob("year_month=*/data_silver.parquet"))
    if not paths:
        raise FileNotFoundError(f"No Silver partitions in {silver_dir}")
    return _read_parquet_partitions(paths)


def read_gold_table(gold_dir: Path, table_name: str) -> pd.DataFrame:
    """Load one Gold table from Parquet."""
    path = gold_dir / table_name / f"{table_name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Gold table not found: {path}")
    return pq.read_table(path).to_pandas()


def compute_layer_metrics(df: pd.DataFrame, layer: str) -> LayerMetrics:
    """Row count, duplicate rate, null rates, and TabularDataQuality summary."""
    row_count = len(df)
    duplicate_rows = int(df.duplicated().sum()) if row_count else 0
    duplicate_rate = round(duplicate_rows / max(row_count, 1), 6)

    null_rates: dict[str, float] = {}
    for col in KEY_COLUMNS:
        if col not in df.columns:
            continue
        null_rates[col] = round(float(df[col].isna().mean()), 6)

    empty_customer_rate = 0.0
    if "customer_id" in df.columns:
        s = df["customer_id"].fillna("").astype(str).str.strip()
        empty_customer_rate = round(float((s == "").mean()), 6)

    dq = TabularDataQuality(df, key_columns=KEY_COLUMNS)
    quality = dq.run_all_checks()

    return LayerMetrics(
        layer=layer,
        row_count=row_count,
        duplicate_rows=duplicate_rows,
        duplicate_rate=duplicate_rate,
        null_rates=null_rates,
        empty_customer_rate=empty_customer_rate,
        quality=quality,
    )


def _rfm_eligible_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Rows that feed RFM: known customer, non-cancellation, positive line_amount."""
    if "line_amount" not in df.columns:
        df = df.copy()
        df["line_amount"] = pd.to_numeric(df["quantity"], errors="coerce") * pd.to_numeric(
            df["price"], errors="coerce"
        )
    mask = (
        (df["customer_id"].fillna("").astype(str).str.strip() != "")
        & (~df["is_cancellation"].astype(bool))
        & (pd.to_numeric(df["line_amount"], errors="coerce") > 0)
    )
    return df.loc[mask]


def _rfm_eligible_revenue(silver: pd.DataFrame) -> float:
    """Revenue base used by RFM: non-cancellation, known customer, positive amount."""
    eligible = _rfm_eligible_frame(silver)
    return float(eligible["line_amount"].sum())


def _rfm_eligible_customer_count(df: pd.DataFrame) -> int:
    """Distinct customers eligible for RFM."""
    return int(_rfm_eligible_frame(df)["customer_id"].nunique())


def _bronze_rfm_eligible_revenue(bronze: pd.DataFrame) -> float:
    """RFM-eligible revenue rebuilt from Bronze (dedup + noise filter + RFM rules)."""
    deduped = bronze.drop_duplicates()
    noise_mask = (~deduped["is_cancellation"].astype(bool)) & (
        pd.to_numeric(deduped["price"], errors="coerce") <= 0
    )
    cleaned = deduped[~noise_mask].copy()
    cleaned["line_amount"] = (
        pd.to_numeric(cleaned["quantity"], errors="coerce")
        * pd.to_numeric(cleaned["price"], errors="coerce")
    )
    return _rfm_eligible_revenue(cleaned)


def check_rfm_reconciliation(
    rfm: pd.DataFrame,
    source: pd.DataFrame,
    *,
    source_layer: str = "silver",
    revenue_tolerance: float = REVENUE_TOLERANCE,
) -> list[str]:
    """RFM monetary vs eligible revenue; customer base; segment counts."""
    issues: list[str] = []

    eligible_revenue = _rfm_eligible_revenue(source)
    rfm_revenue = float(rfm["monetary"].sum())
    if eligible_revenue > 0:
        diff_pct = abs(rfm_revenue - eligible_revenue) / eligible_revenue
        if diff_pct > revenue_tolerance:
            issues.append(
                f"RFM monetary ({rfm_revenue:.2f}) != {source_layer} eligible "
                f"revenue ({eligible_revenue:.2f}), diff={diff_pct:.4%}"
            )

    eligible_customers = _rfm_eligible_customer_count(source)
    if len(rfm) != eligible_customers:
        issues.append(
            f"mart_rfm customers ({len(rfm)}) != {source_layer} eligible "
            f"customers ({eligible_customers})"
        )

    if rfm["customer_id"].duplicated().any():
        issues.append("mart_rfm.customer_id is not unique")

    segment_sum = int(rfm["segment"].value_counts().sum())
    if segment_sum != len(rfm):
        issues.append(
            f"RFM segment counts sum ({segment_sum}) != mart_rfm rows ({len(rfm)})"
        )

    if rfm["segment"].isna().any():
        issues.append("mart_rfm has null segment labels")

    return issues


def _year_month_series(df: pd.DataFrame) -> pd.Series:
    """Derive YYYY-MM partition key from year_month column or invoice_date."""
    if "year_month" in df.columns:
        return df["year_month"].astype(str)
    if "invoice_date" in df.columns:
        return df["invoice_date"].dt.to_period("M").astype(str)
    raise ValueError("DataFrame needs year_month or invoice_date for partition checks")


def partition_row_counts(df: pd.DataFrame) -> dict[str, int]:
    """Row counts per YYYY-MM partition."""
    ym = _year_month_series(df)
    return {str(k): int(v) for k, v in ym.value_counts().sort_index().items()}


def expected_staging_partition_counts(bronze: pd.DataFrame) -> dict[str, int]:
    """Per-partition row counts after dedup + noise filter (mirrors staging SQL)."""
    bronze = bronze.copy()
    bronze["_year_month"] = _year_month_series(bronze)
    counts: dict[str, int] = {}
    for ym, group in bronze.groupby("_year_month", sort=True):
        deduped = group.drop_duplicates()
        noise_mask = (~deduped["is_cancellation"].astype(bool)) & (
            pd.to_numeric(deduped["price"], errors="coerce") <= 0
        )
        counts[str(ym)] = int((~noise_mask).sum())
    return counts


def check_partition_reconciliation(
    expected: dict[str, int],
    actual: dict[str, int],
    label: str,
) -> list[str]:
    """Return issues when per-partition counts diverge."""
    issues: list[str] = []
    all_months = sorted(set(expected) | set(actual))
    for ym in all_months:
        exp = expected.get(ym, 0)
        act = actual.get(ym, 0)
        if exp != act:
            issues.append(
                f"{label} partition {ym}: expected {exp} rows, got {act}"
            )
    return issues


def validate_pipeline_parity(
    gold_dir: Path,
    duckdb_path: Path,
    *,
    revenue_tolerance: float = REVENUE_TOLERANCE,
) -> list[str]:
    """Compare Python Gold Parquet vs dbt DuckDB marts (P1 dual-pipeline parity)."""
    issues: list[str] = []

    try:
        py_fact = read_gold_table(gold_dir, "fact_transactions")
        py_rfm = read_gold_table(gold_dir, "mart_rfm")
    except FileNotFoundError as exc:
        return [str(exc)]

    copy_path: Path | None = None
    con, copy_path = _connect_duckdb_readonly(duckdb_path)
    try:
        db_fact = con.execute("SELECT * FROM fact_transactions").df()
        db_rfm = con.execute("SELECT * FROM mart_rfm").df()
    except Exception as exc:  # noqa: BLE001
        issues.append(f"Cannot read DuckDB marts for parity: {exc}")
        return issues
    finally:
        con.close()
        if copy_path is not None:
            copy_path.unlink(missing_ok=True)
            copy_path.parent.rmdir()

    if len(py_fact) != len(db_fact):
        issues.append(
            f"Python fact rows ({len(py_fact)}) != dbt fact rows ({len(db_fact)})"
        )

    if len(py_rfm) != len(db_rfm):
        issues.append(
            f"Python mart_rfm customers ({len(py_rfm)}) != "
            f"dbt mart_rfm customers ({len(db_rfm)})"
        )

    py_revenue = float(py_rfm["monetary"].sum())
    db_revenue = float(db_rfm["monetary"].sum())
    if py_revenue > 0:
        diff_pct = abs(db_revenue - py_revenue) / py_revenue
        if diff_pct > revenue_tolerance:
            issues.append(
                f"Python vs dbt RFM monetary diff={diff_pct:.4%} "
                f"(python={py_revenue:.2f}, dbt={db_revenue:.2f})"
            )

    py_guest = int((py_fact["customer_sk"] == 0).sum())
    db_guest = int((db_fact["customer_sk"] == 0).sum())
    if py_guest != db_guest:
        issues.append(
            f"Python guest fact rows (customer_sk=0: {py_guest}) != "
            f"dbt ({db_guest})"
        )

    py_neg_line = int((py_fact["line_amount"] < 0).sum())
    db_neg_line = int((db_fact["line_amount"] < 0).sum())
    if py_neg_line != db_neg_line:
        issues.append(
            f"Cancellation row count mismatch (negative line_amount): "
            f"python={py_neg_line}, dbt={db_neg_line}"
        )

    return issues


def compute_bronze_to_silver_delta(bronze: pd.DataFrame) -> BronzeToSilverDelta:
    """Mirror silver_transform.run_cleaning / stg_bronze__transactions logic."""
    bronze_rows = len(bronze)
    deduped = bronze.drop_duplicates()
    after_dedup = len(deduped)
    dedup_removed = bronze_rows - after_dedup

    noise_mask = (~deduped["is_cancellation"].astype(bool)) & (
        pd.to_numeric(deduped["price"], errors="coerce") <= 0
    )
    noise_removed = int(noise_mask.sum())
    cleaned = deduped[~noise_mask]
    after_noise = len(cleaned)

    return BronzeToSilverDelta(
        bronze_rows=bronze_rows,
        after_dedup=after_dedup,
        dedup_removed=dedup_removed,
        after_noise_filter=after_noise,
        noise_removed=noise_removed,
        expected_silver_rows=after_noise,
    )


def validate_parquet_layers(
    bronze_dir: Path,
    silver_dir: Path,
    gold_dir: Path,
    *,
    revenue_tolerance: float = REVENUE_TOLERANCE,
) -> LayerValidationReport:
    """Validate Python Medallion path: Bronze -> Silver -> Gold Parquet."""
    report = LayerValidationReport()

    bronze = read_bronze_partitions(bronze_dir)
    silver = read_silver_partitions(silver_dir)
    report.bronze = compute_layer_metrics(bronze, "bronze")
    report.silver = compute_layer_metrics(silver, "silver")
    report.bronze_to_silver = compute_bronze_to_silver_delta(bronze)

    missing_cols = [c for c in REQUIRED_BRONZE_COLUMNS if c not in bronze.columns]
    if missing_cols:
        report.issues.append(f"Bronze missing required columns: {missing_cols}")

    # ── Bronze -> Silver ──
    if report.silver.row_count > report.bronze.row_count:
        report.issues.append(
            f"Silver rows ({report.silver.row_count}) > Bronze rows "
            f"({report.bronze.row_count})"
        )

    if report.bronze_to_silver:
        delta = report.bronze_to_silver
        if report.silver.row_count != delta.expected_silver_rows:
            report.issues.append(
                f"Silver rows ({report.silver.row_count}) != expected after "
                f"dedup/noise ({delta.expected_silver_rows}): "
                f"dedup_removed={delta.dedup_removed}, "
                f"noise_removed={delta.noise_removed}"
            )

    if report.silver.duplicate_rows > 0:
        report.issues.append(
            f"Silver has {report.silver.duplicate_rows} full-row duplicates"
        )

    if "line_amount" not in silver.columns:
        report.issues.append("Silver missing column: line_amount")

    # Null rate on keys should not increase materially (except documented guest)
    for col in ("invoice", "stock_code", "country"):
        b_null = report.bronze.null_rates.get(col, 0.0)
        s_null = report.silver.null_rates.get(col, 0.0)
        if s_null > b_null + 0.0001:
            report.issues.append(
                f"Null rate increased for {col}: bronze={b_null}, silver={s_null}"
            )

    # N1: PK-like columns must not be null in Silver
    for col in ("invoice", "stock_code", "invoice_date"):
        if col in silver.columns and silver[col].isna().any():
            report.issues.append(f"Silver has null values in required column: {col}")

    report.silver_qty_price = check_negative_qty_price(silver, "silver")
    _apply_negative_qty_price_check(report, report.silver_qty_price)
    report.issues.extend(
        check_quantity_cancellation_consistency(silver, "silver")
    )

    # X5: per-partition Bronze → Silver reconcile
    report.issues.extend(
        check_partition_reconciliation(
            expected_staging_partition_counts(bronze),
            partition_row_counts(silver),
            "Bronze→Silver",
        )
    )

    # ── Gold tables ──
    try:
        fact = read_gold_table(gold_dir, "fact_transactions")
        rfm = read_gold_table(gold_dir, "mart_rfm")
        dim_customer = read_gold_table(gold_dir, "dim_customer")
        dim_product = read_gold_table(gold_dir, "dim_product")
        dim_country = read_gold_table(gold_dir, "dim_country")
        dim_date = read_gold_table(gold_dir, "dim_date")
    except FileNotFoundError as exc:
        report.issues.append(str(exc))
        return report

    report.gold_fact_rows = len(fact)
    report.gold_rfm_customers = len(rfm)

    report.issues.extend(check_fact_cancellation_measure_rules(fact))
    report.issues.extend(check_fact_null_measures(fact))
    report.issues.extend(
        check_fact_quantity_rules(fact, silver, source_layer="silver")
    )

    # Silver -> Fact: full grain (purchases + cancellations)
    if len(fact) != len(silver):
        report.issues.append(
            f"fact_transactions rows ({len(fact)}) != silver rows ({len(silver)})"
        )

    if len(fact) > len(silver):
        report.issues.append(
            f"fact_transactions rows ({len(fact)}) > silver rows ({len(silver)})"
        )

    # X5: per-partition Silver → Fact (via dim_date)
    if "date_sk" in fact.columns and "date" in dim_date.columns:
        fact_with_ym = fact.merge(
            dim_date[["date_sk", "date"]], on="date_sk", how="left"
        )
        fact_with_ym["year_month"] = (
            pd.to_datetime(fact_with_ym["date"]).dt.to_period("M").astype(str)
        )
        report.issues.extend(
            check_partition_reconciliation(
                partition_row_counts(silver),
                partition_row_counts(fact_with_ym),
                "Silver→Fact",
            )
        )

    # Silver layer: negative measures only allowed on cancellations
    if "line_amount" in silver.columns:
        bad_neg = silver.loc[
            (silver["line_amount"] < 0) & (~silver["is_cancellation"].astype(bool))
        ]
        if len(bad_neg):
            report.issues.append(
                f"Silver has {len(bad_neg)} rows with line_amount < 0 "
                "on non-cancellation transactions"
            )

    if fact["transaction_sk"].duplicated().any():
        report.issues.append("fact_transactions.transaction_sk is not unique")

    # FK integrity (guest rows map to customer_sk=0 in Python gold)
    guest_rows = silver["customer_id"].fillna("").astype(str).str.strip() == ""
    expected_guest = int(guest_rows.sum())
    if "customer_sk" in fact.columns:
        actual_guest = int((fact["customer_sk"] == 0).sum())
        if actual_guest != expected_guest:
            report.warnings.append(
                f"customer_sk=0 count ({actual_guest}) != guest rows "
                f"({expected_guest})"
            )

    for fk_col in ("product_sk", "country_sk", "date_sk"):
        null_fk = int(fact[fk_col].isna().sum())
        if null_fk > 0:
            report.issues.append(f"fact_transactions.{fk_col} has {null_fk} nulls")

    # Dimension uniqueness
    for dim_name, dim_df, sk_col in (
        ("dim_customer", dim_customer, "customer_sk"),
        ("dim_product", dim_product, "product_sk"),
        ("dim_country", dim_country, "country_sk"),
        ("dim_date", dim_date, "date_sk"),
    ):
        if dim_df[sk_col].duplicated().any():
            report.issues.append(f"{dim_name}.{sk_col} is not unique")

    # G1: dim_customer known count = distinct silver customers
    known_customers_stg = silver.loc[
        silver["customer_id"].fillna("").astype(str).str.strip() != "", "customer_id"
    ].nunique()
    known_customers_dim = dim_customer.loc[
        dim_customer["customer_id"].fillna("").astype(str).str.strip() != ""
    ].shape[0]
    if known_customers_stg != known_customers_dim:
        report.issues.append(
            f"dim_customer known count ({known_customers_dim}) != "
            f"distinct silver customers ({known_customers_stg})"
        )

    # G4: mart_rfm customers ⊆ dim_customer
    rfm_ids = set(rfm["customer_id"].astype(str))
    dim_ids = set(
        dim_customer.loc[
            dim_customer["customer_id"].fillna("").astype(str).str.strip() != "",
            "customer_id",
        ].astype(str)
    )
    orphan_rfm = rfm_ids - dim_ids
    if orphan_rfm:
        report.issues.append(
            f"mart_rfm has {len(orphan_rfm)} customers not in dim_customer"
        )

    # RFM reconcile: revenue, customer base, segment distribution
    report.issues.extend(
        check_rfm_reconciliation(rfm, silver, source_layer="silver")
    )
    if bronze is not None:
        bronze_rfm_revenue = _bronze_rfm_eligible_revenue(bronze)
        rfm_revenue = float(rfm["monetary"].sum())
        if bronze_rfm_revenue > 0:
            diff_pct = abs(rfm_revenue - bronze_rfm_revenue) / bronze_rfm_revenue
            if diff_pct > revenue_tolerance:
                report.issues.append(
                    f"RFM monetary ({rfm_revenue:.2f}) != bronze eligible "
                    f"revenue ({bronze_rfm_revenue:.2f}), diff={diff_pct:.4%}"
                )

    return report


def _read_staging_from_bronze(con: Any, bronze_dir: Path) -> pd.DataFrame:
    """Rebuild staging from Bronze Parquet using absolute paths (reliable from repo root)."""
    pattern = str((bronze_dir / "year_month=*/data.parquet").resolve())
    return con.execute(
        f"""
        WITH raw AS (
            SELECT * FROM read_parquet('{pattern}',
                filename=false, hive_partitioning=false)
        ),
        deduped AS (SELECT DISTINCT * FROM raw),
        with_line_amount AS (
            SELECT *, quantity * price AS line_amount FROM deduped
        ),
        cleaned AS (
            SELECT * FROM with_line_amount
            WHERE is_cancellation = true OR price IS NULL OR price > 0
        )
        SELECT
            invoice,
            stock_code,
            description,
            quantity,
            price,
            customer_id,
            country,
            is_cancellation,
            line_amount,
            invoice_date,
            original_invoice_date,
            YEAR(invoice_date) AS invoice_year,
            MONTH(invoice_date) AS invoice_month,
            DAY(invoice_date) AS invoice_day,
            QUARTER(invoice_date) AS invoice_quarter,
            DAYOFWEEK(invoice_date) AS invoice_day_of_week,
            WEEK(invoice_date) AS invoice_week,
            STRFTIME(invoice_date, '%Y-%m') AS year_month
        FROM cleaned
        """
    ).df()


def _read_dbt_staging(con: Any, bronze_dir: Path | None) -> pd.DataFrame:
    """Read staging for QA — prefer dbt Silver view, else Silver parquet."""
    import duckdb

    for view in ("stg_silver__transactions", "stg_bronze__transactions"):
        try:
            return con.execute(f"SELECT * FROM {view}").df()
        except duckdb.IOException:
            continue
        except Exception:
            continue

    if bronze_dir is not None:
        silver_dir = bronze_dir.parent / "silver"
        if silver_dir.exists() and list(silver_dir.glob("year_month=*/data_silver.parquet")):
            return read_silver_partitions(silver_dir)

    if bronze_dir is not None and bronze_dir.exists():
        return _read_staging_from_bronze(con, bronze_dir)

    raise FileNotFoundError(
        "Cannot read stg_silver__transactions and no silver/bronze path provided"
    )


def _connect_duckdb_readonly(duckdb_path: Path) -> tuple[Any, Path | None]:
    """Open DuckDB read-only; copy to temp file if another process holds the lock."""
    import shutil
    import tempfile

    import duckdb

    try:
        return duckdb.connect(str(duckdb_path), read_only=True), None
    except duckdb.IOException as exc:
        if "Could not set lock" not in str(exc):
            raise
        copy_dir = Path(tempfile.mkdtemp(prefix="retail_duckdb_"))
        copy_path = copy_dir / duckdb_path.name
        shutil.copy2(duckdb_path, copy_path)
        return duckdb.connect(str(copy_path), read_only=True), copy_path


def validate_dbt_layers(
    duckdb_path: Path,
    bronze_dir: Path | None = None,
    *,
    revenue_tolerance: float = REVENUE_TOLERANCE,
) -> LayerValidationReport:
    """Validate dbt path: Bronze Parquet vs DuckDB staging + marts."""
    report = LayerValidationReport()

    if bronze_dir and bronze_dir.exists():
        bronze = read_bronze_partitions(bronze_dir)
        report.bronze = compute_layer_metrics(bronze, "bronze")
        report.bronze_to_silver = compute_bronze_to_silver_delta(bronze)

    copy_path: Path | None = None
    con, copy_path = _connect_duckdb_readonly(duckdb_path)
    if copy_path is not None:
        report.warnings.append(
            f"retail.duckdb locked by another app; validated copy at {copy_path}"
        )
    try:
        tables = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        }
        has_staging = (
            "stg_silver__transactions" in tables
            or "stg_bronze__transactions" in tables
        )
        required_marts = {"fact_transactions", "mart_rfm", "dim_customer"}
        missing_marts = required_marts - tables
        if not has_staging or missing_marts:
            missing = []
            if not has_staging:
                missing.append("stg_silver__transactions")
            missing.extend(sorted(missing_marts))
            report.issues.append(f"DuckDB missing tables: {missing}")
            return report

        try:
            stg = _read_dbt_staging(con, bronze_dir)
        except Exception as exc:  # noqa: BLE001
            report.issues.append(f"Cannot read staging layer: {exc}")
            return report

        stg_layer_name = "stg_silver__transactions"
        if bronze_dir and bronze_dir.exists():
            try:
                view_count = None
                for view in ("stg_silver__transactions", "stg_bronze__transactions"):
                    try:
                        view_count = con.execute(
                            f"SELECT count(*) FROM {view}"
                        ).fetchone()[0]
                        stg_layer_name = view
                        break
                    except Exception:
                        continue
                if view_count is not None and view_count != len(stg):
                    report.warnings.append(
                        f"{stg_layer_name} view count ({view_count}) != "
                        f"Silver staging rows ({len(stg)}). "
                        "Re-run: cd dbt && dbt run --profiles-dir ."
                    )
            except Exception:
                report.warnings.append(
                    "stg_silver__transactions view unreadable; "
                    "validated staging via Silver parquet / Bronze rebuild."
                )

        fact = con.execute("SELECT * FROM fact_transactions").df()
        rfm = con.execute("SELECT * FROM mart_rfm").df()
        dim_customer = con.execute("SELECT * FROM dim_customer").df()

        report.silver = compute_layer_metrics(stg, stg_layer_name)
        report.gold_fact_rows = len(fact)
        report.gold_rfm_customers = len(rfm)

        if report.bronze_to_silver:
            delta = report.bronze_to_silver
            if report.silver.row_count != delta.expected_silver_rows:
                report.issues.append(
                    f"Staging rows ({report.silver.row_count}) != expected "
                    f"({delta.expected_silver_rows}): dedup_removed="
                    f"{delta.dedup_removed}, noise_removed={delta.noise_removed}"
                )

        if report.bronze and report.silver.row_count > report.bronze.row_count:
            report.issues.append(
                "Staging rows > Bronze rows after DISTINCT/clean"
            )

        if report.silver.duplicate_rows > 0:
            report.issues.append(
                f"Staging has {report.silver.duplicate_rows} full-row duplicates"
            )

        report.silver_qty_price = check_negative_qty_price(stg, stg_layer_name)
        _apply_negative_qty_price_check(report, report.silver_qty_price)
        report.issues.extend(
            check_quantity_cancellation_consistency(stg, stg_layer_name)
        )

        if report.bronze is not None and bronze_dir and bronze_dir.exists():
            report.issues.extend(
                check_partition_reconciliation(
                    expected_staging_partition_counts(bronze),
                    partition_row_counts(stg),
                    "Bronze→Staging",
                )
            )

        # Fact dashboard rules (dbt path)
        stg_for_fact = _try_read_staging_view(con) or stg
        if stg_for_fact is stg and stg_layer_name not in tables:
            report.warnings.append(
                "stg view unreadable; fact reconciled vs Silver parquet / Bronze rebuild."
            )

        report.issues.extend(check_fact_cancellation_measure_rules(fact))
        report.issues.extend(check_fact_null_measures(fact))
        report.issues.extend(
            check_fact_quantity_rules(fact, stg_for_fact, source_layer="staging")
        )

        if len(fact) != len(stg_for_fact):
            report.issues.append(
                f"fact rows ({len(fact)}) != staging rows ({len(stg_for_fact)})"
            )

        if len(fact) > len(stg_for_fact):
            report.issues.append(
                f"fact rows ({len(fact)}) > staging rows ({len(stg_for_fact)})"
            )

        dim_date = con.execute("SELECT * FROM dim_date").df()
        fact_with_ym = fact.merge(
            dim_date[["date_sk", "date"]], on="date_sk", how="left"
        )
        fact_with_ym["year_month"] = (
            pd.to_datetime(fact_with_ym["date"]).dt.to_period("M").astype(str)
        )
        report.issues.extend(
            check_partition_reconciliation(
                partition_row_counts(stg_for_fact),
                partition_row_counts(fact_with_ym),
                "Staging→Fact",
            )
        )

        guest_stg = int(
            (stg_for_fact["customer_id"].fillna("").astype(str).str.strip() == "").sum()
        )
        guest_fact = int((fact["customer_sk"] == 0).sum())
        if guest_stg != guest_fact:
            report.issues.append(
                f"Guest rows: staging ({guest_stg}) != "
                f"fact customer_sk=0 ({guest_fact})"
            )

        bad_neg_stg = stg.loc[
            (stg["line_amount"] < 0) & (~stg["is_cancellation"].astype(bool))
        ]
        if len(bad_neg_stg):
            report.issues.append(
                f"Staging has {len(bad_neg_stg)} rows with line_amount < 0 "
                "on non-cancellation transactions"
            )

        if fact["transaction_sk"].duplicated().any():
            report.issues.append("fact_transactions.transaction_sk not unique")

        known_customers_stg = stg.loc[
            stg["customer_id"].fillna("").astype(str).str.strip() != "", "customer_id"
        ].nunique()
        known_customers_dim = dim_customer.loc[
            dim_customer["customer_id"].fillna("").astype(str).str.strip() != ""
        ].shape[0]
        if known_customers_stg != known_customers_dim:
            report.issues.append(
                f"dim_customer known count ({known_customers_dim}) != "
                f"distinct staging customers ({known_customers_stg})"
            )

        rfm_ids = set(rfm["customer_id"].astype(str))
        dim_ids = set(
            dim_customer.loc[
                dim_customer["customer_id"].fillna("").astype(str).str.strip() != "",
                "customer_id",
            ].astype(str)
        )
        orphan_rfm = rfm_ids - dim_ids
        if orphan_rfm:
            report.issues.append(
                f"mart_rfm has {len(orphan_rfm)} customers not in dim_customer"
            )

        null_product = int(fact["product_sk"].isna().sum())
        null_country = int(fact["country_sk"].isna().sum())
        null_date = int(fact["date_sk"].isna().sum())
        if null_product or null_country or null_date:
            report.issues.append(
                f"fact FK nulls: product={null_product}, country={null_country}, "
                f"date={null_date}"
            )

        report.issues.extend(
            check_rfm_reconciliation(rfm, stg, source_layer="staging")
        )
        if bronze_dir is not None and bronze_dir.exists():
            bronze = read_bronze_partitions(bronze_dir)
            bronze_rfm_revenue = _bronze_rfm_eligible_revenue(bronze)
            rfm_revenue = float(rfm["monetary"].sum())
            if bronze_rfm_revenue > 0:
                diff_pct = abs(rfm_revenue - bronze_rfm_revenue) / bronze_rfm_revenue
                if diff_pct > revenue_tolerance:
                    report.issues.append(
                        f"RFM monetary ({rfm_revenue:.2f}) != bronze eligible "
                        f"revenue ({bronze_rfm_revenue:.2f}), diff={diff_pct:.4%}"
                    )
    finally:
        con.close()
        if copy_path is not None:
            copy_path.unlink(missing_ok=True)
            copy_path.parent.rmdir()

    return report
