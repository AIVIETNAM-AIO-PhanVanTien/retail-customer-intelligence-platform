"""Data quality checks for tabular retail data (ACM1-30, ACM1-40).

Adapts the TextDataQuality pattern from the email-spam project
for multi-column tabular/retail data.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


class TabularDataQuality:
    """Quality-check engine for tabular retail DataFrames.

    Usage::

        dq = TabularDataQuality(df)
        report = dq.run_all_checks()
        summary = dq.summary_df()
    """

    def __init__(self, df: pd.DataFrame, key_columns: list[str] | None = None):
        self.df = df.copy()
        self.key_columns = key_columns or [
            "invoice",
            "stock_code",
            "customer_id",
            "country",
        ]

    # ------------------------------------------------------------------
    # Completeness
    # ------------------------------------------------------------------
    def check_completeness(self) -> dict[str, Any]:
        total = len(self.df)
        col_report: dict[str, dict] = {}
        for col in self.df.columns:
            s = self.df[col]
            null_count = int(s.isna().sum())
            info: dict[str, Any] = {
                "null_count": null_count,
                "null_rate": round(null_count / max(total, 1), 4),
            }
            if s.dtype == object or pd.api.types.is_string_dtype(s):
                s_str = s.fillna("").astype(str).str.strip()
                info["empty_string_rate"] = round(
                    (s_str == "").sum() / max(total, 1), 4
                )
                # whitespace-only = was non-empty before strip, empty after
                s_before = s.fillna("").astype(str)
                whitespace_only = ((s_before.str.strip() == "") & (s_before != "")).sum()
                info["whitespace_only_rate"] = round(
                    whitespace_only / max(total, 1), 4
                )
            col_report[col] = info
        return {"total_rows": total, "columns": col_report}

    # ------------------------------------------------------------------
    # Uniqueness
    # ------------------------------------------------------------------
    def check_uniqueness(self) -> dict[str, Any]:
        col_report: dict[str, dict] = {}
        for col in self.key_columns:
            if col not in self.df.columns:
                continue
            s = self.df[col].dropna()
            n_unique = int(s.nunique())
            total = len(s)
            dup_rate = round(1 - n_unique / max(total, 1), 4)
            top_dups = (
                s.value_counts()
                .head(5)
                .to_dict()
            )
            col_report[col] = {
                "n_unique": n_unique,
                "unique_rate": round(n_unique / max(total, 1), 4),
                "duplicate_rate": dup_rate,
                "top_duplicates": {str(k): int(v) for k, v in top_dups.items()},
            }
        return col_report

    # ------------------------------------------------------------------
    # Consistency (business rules)
    # ------------------------------------------------------------------
    def check_consistency(self) -> dict[str, Any]:
        total = len(self.df)
        report: dict[str, Any] = {}

        # quantity < 0 should only happen for cancellations
        if "quantity" in self.df.columns and "is_cancellation" in self.df.columns:
            neg_qty = self.df["quantity"] < 0
            canc = self.df["is_cancellation"] == True  # noqa: E712
            report["quantity_negative_not_cancellation"] = int(
                (neg_qty & ~canc).sum()
            )
            report["cancellation_positive_quantity"] = int(
                (canc & ~neg_qty).sum()
            )

        # price should never be negative
        if "price" in self.df.columns:
            report["price_negative_count"] = int((self.df["price"] < 0).sum())

        # line_amount == quantity * price
        if all(c in self.df.columns for c in ("line_amount", "quantity", "price")):
            expected = self.df["quantity"] * self.df["price"]
            diff = (self.df["line_amount"] - expected).abs()
            report["line_amount_mismatch_count"] = int((diff > 0.01).sum())

        # cancellation flag vs invoice prefix
        if "invoice" in self.df.columns and "is_cancellation" in self.df.columns:
            has_c_prefix = self.df["invoice"].str.startswith("C", na=False)
            flag_mismatch = has_c_prefix != self.df["is_cancellation"]
            report["cancellation_flag_mismatch"] = int(flag_mismatch.sum())

        return report

    # ------------------------------------------------------------------
    # Value ranges
    # ------------------------------------------------------------------
    def check_value_ranges(self) -> dict[str, Any]:
        report: dict[str, Any] = {}
        for col in ("quantity", "price", "line_amount"):
            if col not in self.df.columns:
                continue
            s = self.df[col].dropna()
            report[f"{col}_min"] = float(s.min()) if len(s) else None
            report[f"{col}_max"] = float(s.max()) if len(s) else None
            report[f"{col}_mean"] = round(float(s.mean()), 4) if len(s) else None
            report[f"{col}_zero_count"] = int((s == 0).sum())
            if col == "quantity":
                report["quantity_negative_count"] = int((s < 0).sum())
        return report

    # ------------------------------------------------------------------
    # Temporal
    # ------------------------------------------------------------------
    def check_temporal(self) -> dict[str, Any]:
        report: dict[str, Any] = {}
        date_col = "invoice_date"
        if date_col not in self.df.columns:
            return report

        s = pd.to_datetime(self.df[date_col], errors="coerce").dropna()
        if len(s) == 0:
            return report

        report["date_min"] = str(s.min())
        report["date_max"] = str(s.max())
        report["date_range_days"] = int((s.max() - s.min()).days)

        # check for month gaps
        months = sorted(s.dt.to_period("M").unique())
        report["unique_months"] = len(months)
        if len(months) > 1:
            gaps = 0
            for i in range(1, len(months)):
                diff = months[i] - months[i - 1]
                if diff.n > 1:
                    gaps += diff.n - 1
            report["month_gaps"] = gaps
        return report

    # ------------------------------------------------------------------
    # Aggregate runner
    # ------------------------------------------------------------------
    def run_all_checks(self) -> dict[str, Any]:
        return {
            "completeness": self.check_completeness(),
            "uniqueness": self.check_uniqueness(),
            "consistency": self.check_consistency(),
            "value_ranges": self.check_value_ranges(),
            "temporal": self.check_temporal(),
        }

    # ------------------------------------------------------------------
    # Flat summary for display / logging
    # ------------------------------------------------------------------
    def summary_df(self) -> pd.DataFrame:
        report = self.run_all_checks()
        rows: list[dict[str, Any]] = []

        def _flatten(obj: Any, category: str, prefix: str = "") -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    path = f"{prefix}.{k}" if prefix else k
                    if isinstance(v, dict):
                        _flatten(v, category, path)
                    else:
                        rows.append(
                            {"category": category, "metric": path, "value": v}
                        )

        for cat, metrics in report.items():
            _flatten(metrics, cat)

        return pd.DataFrame(rows)
