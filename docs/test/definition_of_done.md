# Definition of Done (DoD) — All 4 Sprints

This document defines the "Definition of Done" (DoD) for each sprint in the Retail Customer Intelligence Platform project. The DoD establishes consistent exit criteria and ensures deliverables meet quality standards before a sprint demo or handover.

Each sprint has core items that must be completed for the sprint to be considered done. These criteria cover documentation, code, data, tests, pipeline, and review/sign-off.

---

# Sprint 1 — Discovery & Onboarding (DoD)

- Documentation
  - BRD (Business Requirements Document) completed and reviewed.
  - UML diagrams (Use Case, Activity, Sequence) drafted and available in `docs/`.
  - Solution architecture and data flow documented (`docs/Solution_Architecture.md`).
  - ML Design high-level doc (`docs/ml_design.md`) present.

- Repo and environment
  - Repository skeleton and folder structure created.
  - `docker-compose.yml` skeleton with Airflow, dbt, DuckDB, MLflow defined.
  - README updated with quickstart and run instructions.

- Data
  - Initial EDA notebooks and `docs/data_dictionary.xlsx` created.
  - Source data format and date-shift convention documented.

- QA & tests
  - Test plan (`docs/test_plan.md`) and checklist for Sprint 1 available.
  - Acceptance criteria for Sprint 2 agreed.

- Review & sign-off
  - Sprint 1 demo completed and feedback logged as issues.
  - Team Lead and QA sign-off on README, BRD, UML, Docker skeleton.

---

# Sprint 2 — Data Platform MVP (DoD)

- Data pipeline
  - Bronze ingest implemented: CSV → Parquet (immutable) with ingest audit log.
  - Silver cleaning + dedup + date-shift implemented and documented.
  - Gold star schema implemented: `dim_customer`, `dim_product`, `dim_date`, `dim_country`, `fact_transactions`.

- dbt and Airflow
  - dbt project structure (staging → intermediate → marts) implemented.
  - dbt models for star schema and initial RFM mart present.
  - dbt tests for `unique`, `not_null`, `accepted_values`, and `relationships` added.
  - Airflow DAG for `ingest → clean → dbt run → dbt test → publish Gold` created and runnable locally.

- Validation & QA
  - Validation logs for row counts, nulls, duplicates, FK integrity produced.
  - RFM totals reconcile with raw revenue within acceptable tolerance.
  - Test Plan updated; Sprint 2 checklist fully executed.

- Documentation & demo
  - Data dictionary updated for Gold RFM mart.
  - End-to-end demo `CSV → Airflow → dbt → Star Schema → RFM` completed.
  - QA sign-off: High/Critical issues resolved or explicitly accepted.

---

# Sprint 3 — ML Layer & Analytics (DoD)

- Features & model
  - Feature mart implemented (`mart_customer_features`) with required features (R, F, M, AOV, LTV, tenure, order patterns).
  - Model training pipeline implemented: reproducible training run logged to MLflow.
  - Models (Logistic Regression + XGBoost) trained with evaluation metrics (AUC, precision, recall, F1) documented.

- Integration
  - Batch scoring pipeline added to Airflow: `train_model → score_customers → publish predictions`.
  - MLflow tracking server running and experiments logged; model registry used for candidate models.

- Tests & validation
  - Model tests: feature schema checks, value range checks, and AUC gate (documented target) executed.
  - Data quality tests run on feature mart and KPI marts.

- Explainability & analytics
  - SHAP or feature importance view prepared for top churn drivers.
  - Key KPI marts for dashboard ready (revenue by month, retention, cohort metrics).

- Documentation & demo
  - ML design and model evaluation documented.
  - Sprint 3 demo: `Customer → Features → Model → Churn Probability` completed.
  - QA and Tech Lead sign-off with High/Critical defects resolved or accepted.

---

# Sprint 4 — Dashboard, CI/CD & Final Delivery (DoD)

- Dashboard & UX
  - Power BI report or Streamlit demo provides RFM segments, churn-risk view, cohort visualizations, and exportable retention lists.
  - Dashboard numbers reconcile with Gold tables.

- CI/CD & packaging
  - GitHub Actions pipeline (`.github/workflows/ci.yml`) configured: lint → dbt test → pytest → docker build.
  - Final `docker-compose.yml` builds and runs the demo stack reproducibly.

- Monitoring & ops
  - Basic monitoring: ingestion freshness, row counts, null rates logged to monitoring table.
  - Model monitoring indicators defined (prediction distribution, scoring volume); lightweight alerts implemented.

- Documentation & release
  - Business Impact Report completed (`docs/business_impact.md`).
  - LaTeX Technical Report and presentation slides prepared.
  - Release tagged `v1.0` on `main`.

- Acceptance
  - Final QA report and UAT sign-off completed.
  - No open High/Critical defects; known Medium/Low defects documented with plans.
  - Final demo recorded and handed to Team Lead.

---

# Handover and archive

- All artifacts (docs, notebooks, dbt, DAGs, models, charts) stored in `docs/`, `notebooks/`, `dbt/`, `airflow/dags/`, and `ml/`.
- Final retrospective notes and backlog items for follow-up included in Jira.