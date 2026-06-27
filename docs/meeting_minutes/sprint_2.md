# Meeting Minutes — Sprint 2 Review & Sprint 3 Planning

**Date:** 18 June 2026 · 22:00 ICT
**Project:** Retail Customer Intelligence Platform (ACM1)
**Attendees:** Phan Văn Tiến, Võ Ngọc Gia Bảo, Phúc Nhân Nguyễn, Ngọc Phương, Hoàng Đức Kiên

---

## Sprint 2 Demo — What was delivered

| Component | Owner | Status |
|---|---|---|
| Bronze ingest (CSV → Parquet, audit log, date-shift) | Data | ✅ Done |
| Silver transform (clean, dedup, type-cast, validate) | Data | ✅ Done |
| Gold star schema (`fact_transactions` + 4 dims) | Data | ✅ Done |
| RFM mart (`mart_rfm` — quintiles + segment labels) | Model | ✅ Done |
| dbt models (staging → intermediate → marts) | Pipeline | ✅ Done |
| dbt tests (35 custom SQL assertions) | Pipeline | ✅ Done |
| Airflow DAG (ingest → clean → dbt run → dbt test) | Pipeline | ✅ Done |
| Data quality validation (QA) | QA | ✅ Done |

---

## Key Decisions Made

### 1. Date rebasing approach
- Decided to shift dates at Bronze ingest time (not Silver) so the immutable raw layer remains original, but partitioned Bronze reflects rebased calendar
- **Reason:** keeps Silver and downstream layers consistent without re-deriving offsets

### 2. Churn label definition
- A customer is churned if no purchase in the **last 90 days** from the observation cutoff
- **Reason:** 90-day window aligns with the retail industry standard and covers ~3 purchasing cycles in this dataset

### 3. dbt profile — two targets
- `dev`: relative path `../data/retail.duckdb` (local runs from `dbt/` directory)
- `prod`: absolute path `/opt/airflow/data/retail.duckdb` (Airflow container)
- **Reason:** avoids path-related failures in Docker without hardcoding absolute paths in dev

### 4. Guest customers excluded
- Transactions without `Customer ID` treated as anonymous guest orders and excluded from customer-level analytics
- **Reason:** cannot compute RFM or churn for unidentified customers; ~25% of rows affected

---

## Issues & Resolutions

| Issue | Resolution |
|---|---|
| dbt `tests` key deprecated → should be `data_tests` | Kept as `tests` for dbt 1.8.x compatibility; will migrate in future sprint |
| Negative quantities in non-cancellation rows | Flagged and quarantined in Silver; dbt test `assert_stg_negative_qty_price_rules` validates |
| RFM quintile edge case: customers with identical scores | Resolved with `rank(method='first')` to ensure unique quintile assignments |

---

## Sprint 3 Plan

| Owner | Tasks |
|---|---|
| Data | KPI marts (revenue by month, cohort, segment distribution) |
| Model | Feature engineering (32 features) · Train LR + XGBoost · Evaluate (AUC, F1) · Batch scoring |
| Pipeline | Extend Airflow DAG (train → score → publish) · MLflow tracking server |
| QA | Model validation (feature schema, value ranges, AUC gate > 0.80) |
| Tech Lead | PR reviews for ML pipeline and feature engineering |

---

## Next Meeting

**Date:** 25 June 2026 · 22:00 ICT — Sprint 3 Demo
