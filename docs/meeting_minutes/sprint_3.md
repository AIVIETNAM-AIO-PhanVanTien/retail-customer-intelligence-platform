# Meeting Minutes — Sprint 3 Review & Sprint 4 Planning

**Date:** 25 June 2026 · 22:00 ICT
**Project:** Retail Customer Intelligence Platform (ACM1)
**Attendees:** Phan Văn Tiến, Võ Ngọc Gia Bảo, Phúc Nhân Nguyễn, Ngọc Phương, Hoàng Đức Kiên

---

## Sprint 3 Demo — What was delivered

| Component | Owner | Status |
|---|---|---|
| 32 engineered features (RFM + behavioral + trend) | Model | ✅ Done |
| Churn model: XGBoost sklearn Pipeline | Model | ✅ Done |
| Batch scoring (`churn_probability` + `churn_flag`) | Model | ✅ Done |
| MLflow experiment tracking + model registry | Pipeline | ✅ Done |
| Airflow DAG extended (train → score → publish) | Pipeline | ✅ Done |
| KPI marts (`mart_kpi_monthly`) | Data | ✅ Done |
| Model validation tests (AUC gate, feature schema) | QA | ✅ Done |

---

## Key Decisions Made

### 1. XGBoost chosen over Logistic Regression
- Both models were trained; XGBoost outperformed LR significantly on AUC
- **Decision:** ship XGBoost as the primary model; LR retained in MLflow for reference
- **Reason:** business impact requires the best possible precision at the retention-list threshold

### 2. Threshold selection — 0.5 default, tunable in app
- Optimal threshold computed on validation set; stored in `metadata.json`
- Streamlit app exposes a slider so Marketing can adjust without code changes
- **Reason:** different campaigns may warrant different precision/recall trade-offs

### 3. MLflow artifact storage — file-based (local `mlruns/`)
- No remote tracking server in local dev; Docker volume mounts `mlruns/`
- **Trade-off acknowledged:** loses centralized multi-user tracking, acceptable for 5-person team
- Cloud path documented in `docs/planning/Project_Plan.md §8` (Azure MLflow)

### 4. Feature store approach — DuckDB mart (`mart_features`)
- Features computed in dbt Gold layer, served via DuckDB query in training pipeline
- **Reason:** no additional infrastructure needed; dbt tests validate feature correctness

---

## Issues & Resolutions

| Issue | Resolution |
|---|---|
| AUC gate (>0.80) not met on first training run | Added `monetary_acceleration` and `velocity_ratio_30d_90d` features; AUC improved |
| `scikit-learn` version mismatch when loading pickled model | Pinned `scikit-learn==1.7.2` in `app/requirements.txt`; documented in `app/README.md` |
| Airflow DAG import errors for dbt paths inside container | Fixed via `--vars` override passing absolute paths from Airflow environment |

---

## Sprint 4 Plan

| Owner | Tasks | Priority |
|---|---|---|
| Data | Power BI dashboard (RFM, KPIs, churn-risk, cohort) | P0 |
| Model | SHAP feature importance · K-Means clustering | P0 |
| Pipeline | GitHub Actions CI/CD · Docker finalize · Streamlit HF Spaces · Monitoring | P0 |
| QA | UAT (Power BI numbers vs Gold tables) · Final QA report | P0 |
| Tech Lead | Business Impact Report · Presentation slides · Release tag v1.0 | P0 |
| ALL | LaTeX Technical Report (4 sections by role) | P0 |
| Team Leader | Demo video (end-to-end walkthrough) | P0 |

**Deadline: 30 June 2026 (Tuesday)**

---

## Next Meeting

**Date:** 30 June 2026 · Final delivery review
