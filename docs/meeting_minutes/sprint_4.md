# Meeting Minutes — Sprint 4 Review & Final Delivery

**Date:** 30 June 2026 · 22:00 ICT
**Project:** Retail Customer Intelligence Platform (ACM1)
**Attendees:** Phan Văn Tiến, Võ Ngọc Gia Bảo, Phúc Nhân Nguyễn, Ngọc Phương, Hoàng Đức Kiên

---

## Sprint 4 Demo — What was delivered

| Component | Owner | Status |
|---|---|---|
| K-Means customer clustering (3 clusters, SHAP explainability) | Model | ✅ Done |
| SHAP feature importance (global + per-customer) | Model | ✅ Done |
| Streamlit serving app (churn + clustering + monitoring tabs) | Pipeline | ✅ Done |
| HuggingFace Spaces deployment (public demo) | Pipeline | ✅ Done |
| GitHub Actions CI/CD (lint → dbt test → pytest → docker build) | Pipeline | ✅ Done |
| Model + data drift monitoring (`mart_monitoring`) | Pipeline | ✅ Done |
| Power BI / Fabric dashboard (Business Performance + Customer Intelligence) | Data | ✅ Done |
| Fabric CSV export pipeline (`scripts/export_powerbi.py --format csv`) | Data | ✅ Done |
| UAT — Power BI numbers reconciled with Gold tables | QA | ✅ Done |
| Technical Report (LaTeX, 4 sections by role) | ALL | ✅ Done |
| Release tag `v1.0` | Tech Lead | ✅ Done |

---

## Key Decisions Made

### 1. Fabric over local Power BI
- Dashboard published to **Microsoft Fabric** (school tenant) instead of local Power BI Desktop
- **Reason:** enables team-wide access via browser without distributing `.pbix` files
- `.pbix` files also committed to `dashboard/` for offline portability

### 2. Fabric public embed not available
- "Publish to web" blocked by school tenant admin policy
- **Decision:** use HuggingFace Streamlit app as the public-facing demo; Fabric dashboard for internal/grader review
- **Reason:** Streamlit app already covers the same visuals and is fully accessible without login

### 3. mart_features excluded from Fabric export
- `mart_features` (33 ML input columns) excluded from the CSV export for Fabric
- **Reason:** not meaningful for BI dashboards; only used as churn model input
- `mart_monitoring` excluded as well — already served via Streamlit monitoring tab

### 4. Clustering labels finalized
- 3 clusters labeled: **High-Value**, **Mid-Tier**, **Occasional**
- Labels derived from cluster profile stats (monetary + frequency + recency)
- Stored in `ml/artifacts/clustering/metadata.json`

---

## Issues & Resolutions

| Issue | Resolution |
|---|---|
| `COPY ... TO` on DuckDB read-only connection failed for gold parquet views | Switched to in-memory DuckDB + `ATTACH retail.duckdb (READ_ONLY)`; created gold views in memory |
| Active Customers card showing 25K (SUM of monthly counts) | Replaced with `DISTINCTCOUNT(fact_transactions[customer_sk])` = 5,921 |
| AOV card required DAX — `DIVIDE(SUM(revenue), SUM(orders))` | Created DAX measure in Fabric semantic model |
| Cancellation Rate required DAX | Created DAX measure: `cancelled_orders / (orders + cancelled_orders)` |
| Slicer dropdown not available in new Fabric slicer | Converted to classic visual → Style → Dropdown |

---

## Final Metrics

| Metric | Value |
|---|---|
| Net Revenue | £15.70M |
| Total Orders | 36,457 |
| Active Customers | 5,921 |
| AOV | £465 |
| Units Sold | 10.28M |
| Cancellation Rate | 18.4% |
| Churn Model AUC | > 0.80 (gate passed) |
| dbt tests passing | 35 / 35 |
| CI/CD pipeline | ✅ Green |

---

## Project Retrospective

### What went well
- SDLC-first approach kept scope under control — BRD → UML → Star Schema → dbt → ML → Dashboard chain was coherent end-to-end
- dbt test suite (35 assertions) caught multiple data quality issues early (negative quantities, anomalous cancellations, RFM reconciliation)
- MLflow experiment tracking made model comparison reproducible
- Docker Compose one-command stack worked as designed

### What could be improved
- `mart_features` and `mart_churn_scores` not materialized in DuckDB — required separate parquet handling in export script
- Power BI embed blocked by tenant policy — plan for personal Fabric account in future projects
- Date rebasing applied at Bronze layer — works but adds a hidden offset that needs documentation for new contributors

---

## Deliverables Handed Over

| Artefact | Location |
|---|---|
| Full repo | GitHub · branch `main` · tag `v1.0` |
| Streamlit demo | HuggingFace Spaces (public) |
| Fabric dashboard | Microsoft Fabric · school tenant |
| `.pbix` files | `dashboard/` in repo |
| Technical Report | `docs/` (PDF + LaTeX source) |
| Jira board | `ACM1` — all tickets closed |

---

## Meeting Closed

**30 June 2026 · 22:45 ICT** — Project ACM1 officially completed.
