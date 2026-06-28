# Test Plan & QA Checklist (English)

Project: Retail Customer Intelligence Platform
Scope: Sprint 1, Sprint 2, Sprint 3 & Sprint 4
Owner: QA / Reviewer
Reference: `Project_Plan.md`, `README.md`

---

## 1. What is a Test Plan?

A test plan is a document that describes the strategy, objectives, scope, schedule, resources, and exit criteria for testing a release or a feature.

For this project, the test plan serves to align how QA will verify:

- what is in scope for all four sprints;
- how testing will be performed and what criteria apply;
- who is responsible for each testing task;
- when testing should stop, be suspended, or resume;
- what deliverables are required so the next sprint does not have to rework foundational items.

According to best practices, the test plan should cover four main areas: **scope**, **method**, **responsibilities**, and **control criteria**.

---

## 2. QA Objectives

The QA objectives across all four sprints are to ensure the team is aligned from the start, reduce the risk of incorrect implementation, and confirm the data platform delivers reliable outputs end-to-end from raw CSV to dashboard and ML serving.

QA will focus on four layers across all sprints:

- Requirements correctness: align with the BRD, scope, deliverables, and priority.
- Logical correctness: data flow, star schema, cleaning rules, RFM segmentation, ML pipeline, and dashboard numbers must be consistent.
- Integration correctness: end-to-end pipeline from CSV → Bronze → Silver → Gold → ML → Dashboard must be reproducible.
- Readiness to deliver: documentation, CI/CD, test coverage, and UAT sign-off must be complete before final release.

---

## 3. Scope of the Test Plan

### 3.1 Sprint 1

Sprint 1 testing scope focuses on:

- BRD, scope, stakeholders, objectives, success criteria
- UML: Use Case, Activity, Sequence diagrams
- Solution Architecture / data flow
- Data profiling, data dictionary, source analysis
- ML design and churn / RFM definition at a high level
- Repo setup, branch conventions, folder structure
- Docker Compose skeleton for Airflow, dbt, DuckDB, MLflow
- Definition of Done and test checklist

### 3.2 Sprint 2

Sprint 2 testing scope focuses on:

- Bronze ingest from CSV to Parquet / immutable layer
- Silver cleaning, deduplication, date-shift, schema validation
- Gold star schema: `dim_customer`, `dim_product`, `dim_date`, `dim_country`, `fact_transactions`
- dbt project structure and dbt tests
- Airflow DAG: `ingest → clean → dbt run → dbt test → publish Gold`
- RFM scoring logic and segmentation labels
- Validation logs for row counts, nulls, duplicates, FK integrity, revenue reconciliation

### 3.3 Sprint 3

Sprint 3 testing scope focuses on:

- Feature engineering: 32 features (RFM + behavioral + trend + velocity)
- Churn model: XGBoost sklearn Pipeline — training, evaluation, MLflow tracking
- Batch scoring: `churn_probability`, `churn_flag`, `risk_tier` per customer
- Model validation: AUC gate (> 0.80), feature schema, value ranges
- `mart_features` and `mart_churn_scores` correctness
- Airflow DAG extension: `train → score → publish`
- MLflow experiment tracking and model registry

### 3.4 Sprint 4

Sprint 4 testing scope focuses on:

- K-Means clustering: 3 clusters, SHAP explainability
- Streamlit serving app: churn + clustering + monitoring tabs
- HuggingFace Spaces deployment: public accessibility
- GitHub Actions CI/CD: lint → dbt test → pytest → docker build pipeline
- Model and data drift monitoring: `mart_monitoring` metrics
- Power BI / Fabric dashboard: Business Performance + Customer Intelligence pages
- UAT: dashboard KPI numbers reconcile with Gold tables
- CSV export pipeline: `scripts/export_powerbi.py --format csv`

---

## 4. Test Objectives and Metrics

### 4.1 Objectives

The testing objectives are to:

- verify the product implements the functionality described in the BRD;
- validate that input and output data behave as expected;
- ensure pipelines, models and dashboard run correctly in the defined environment;
- reduce the risk of logic, data, and integration defects before internal release.

### 4.2 Metrics

QA metrics to track during Sprints 1 and 2:

- defect counts by severity
- test coverage mapped to requirements
- row count consistency across layers
- null rate for key columns
- duplicate counts
- FK integrity pass rate
- revenue reconciliation between raw and RFM mart
- number of valid segment labels

### 4.3 Pass / Fail

- Pass: outputs meet requirements, data reconciles, and no High/Critical open defects remain.
- Fail: the output violates requirements, core logic is incorrect, validation is missing, or results cannot be reliably re-run/re-checked.

---

## 5. Test Deliverables

### 5.1 Before testing

- this test plan
- test checklists for Sprint 1 and Sprint 2
- test design and environment specifications

### 5.2 During testing

- test logs
- defect reports
- test data / sample data notes
- validation logs for Bronze / Silver / Gold / RFM

### 5.3 After testing

- test summary report
- QA sign-off note
- issues list to hand over to Sprint 3

---

## 6. Test Strategy

### 6.1 Approach

QA will apply a four-layer approach:

1. Document review: check BRD / UML / architecture / data dictionary align with project scope.
2. Logic review: verify data rules, schema mappings, RFM rules, edge cases and step dependencies.
3. Implementation review: inspect repo structure, Docker Compose, DAGs, dbt models, naming conventions.
4. Validation review: ensure outputs can be reconciled with data, have clear logs, and are re-checkable after fixes.

### 6.2 Test Types

- manual review
- smoke tests for the pipeline skeleton
- regression review using the checklist
- integration testing for Airflow / dbt / data flow
- data quality testing for Bronze / Silver / Gold layers

### 6.3 Risks and Assumptions

- Assumptions: the source data is sufficient to build Bronze / Silver / Gold and the team agrees on handling rules before QA signs off.
- Risks: scope misunderstandings, incorrect date-shift, RFM rule divergences, insufficient validation, environment or dependency issues, and compressed timelines near sprint end.

### 6.4 Stop / Suspend / Resume Criteria

- Stop criterion: stop testing an item when it meets its stated objectives and all required checks pass.
- Suspend criterion: suspend testing when a foundational blocker occurs (e.g., schema mismatch, DAG dependency error, unreconciled data).
- Resume criterion: resume after fixes are implemented and there is clear evidence to re-check the original failure points and related checks.

### 6.5 Resources and Timeline

- Resources: QA needs access to the repo, BRD / UML / data dictionary, Docker Compose, and outputs from dbt / Airflow / RFM.
- Timeline: perform reviews throughout the sprint rather than waiting for the sprint end.

---

## 7. Test Environment and Test Data

### 7.1 Environment

- local machine
- Docker Compose
- Airflow
- dbt + DuckDB
- MLflow
- file-based dataset / CSV input

### 7.2 Test Data

- `online_retail_listing.csv` or an equivalent agreed dataset
- sample data for smoke tests
- test data for edge cases: nulls, duplicates, outliers, invalid FKs, revenue mismatch

### 7.3 Environment Checks

- the environment must be able to run reproducibly
- service configurations must not conflict with README and Project_Plan
- test data must be sufficient to reproduce validation results

---

## 8. QA Checklist — Sprint 1

### 8.1 BRD and Scope

- [ ] Pain points correctly describe the retail retention / churn problem.
- [ ] Objectives include measurable metrics.
- [ ] Stakeholders align with dashboard and retention list usage.
- [ ] In-scope and out-of-scope items are clearly defined.
- [ ] Success criteria are verifiable after build.

### 8.2 UML and Solution Architecture

- [ ] Use Case diagram includes main actors: Marketing Manager, Data Analyst, ML Engineer, System.
- [ ] Activity diagram shows ingest → validate → RFM → score → publish flow.
- [ ] Sequence diagram shows dashboard → API → feature store → model interactions.
- [ ] Diagrams align with README and Project_Plan narratives.

### 8.3 Data Profiling and Data Dictionary

- [ ] Source data is identified.
- [ ] Data types, keys, and important fields are listed.
- [ ] Date-shift conventions are documented.
- [ ] Columns required for RFM, churn, and star schema are highlighted.
- [ ] Data dictionary includes business keys, transaction keys, and dimension candidates.

### 8.4 Repo Setup and Conventions

- [ ] Folder structure matches the plan.
- [ ] Branch / naming conventions are documented.
- [ ] README/docs describe how to run the minimal project.
- [ ] Docker Compose skeleton includes the MVP services.
- [ ] No conflicting configuration between README and Project_Plan.

### 8.5 Definition of Done for Sprint 1

- [ ] BRD, UML, architecture, data profiling, ML design, repo skeleton, and Docker skeleton are available.
- [ ] Deliverables are readable and reviewable.
- [ ] No major inconsistencies between strategy documents and the team’s intended implementation.
- [ ] Team has agreed the Sprint 2 review criteria.

---

## 9. QA Checklist — Sprint 2

### 9.1 Bronze layer

- [ ] CSV ingest completes successfully.
- [ ] Raw data is stored immutably.
- [ ] Audit logs or ingest evidence exist.
- [ ] Schema enforcement applies.
- [ ] Ingest row counts match source after removing legitimately invalid records.

### 9.2 Silver layer

- [ ] Data cleaned according to agreed rules.
- [ ] Duplicates handled per the agreed rule.
- [ ] Date-shift logic applied consistently.
- [ ] Null handling is documented.
- [ ] Reasons for dropping/keeping records are explainable.

### 9.3 Gold star schema

- [ ] `dim_customer` contains business key and fields required for segmentation.
- [ ] `dim_product` normalizes product attributes appropriately.
- [ ] `dim_country` and `dim_date` serve as conformed dimensions.
- [ ] `fact_transactions` contains the expected measures.
- [ ] Foreign keys between fact and dimensions are valid.
- [ ] No duplication logic breaks the fact table grain.

### 9.4 dbt models and dbt tests

- [ ] dbt structure includes staging / intermediate / marts.
- [ ] Tests for `unique`, `not_null`, `accepted_values`, and `relationships` are present where applicable.
- [ ] Model and column names match the data dictionary.
- [ ] `dbt run` and `dbt test` are reproducible.
- [ ] Test failures must indicate the table, column, and reason.

### 9.5 Airflow DAG

- [ ] DAG models the `ingest → clean → dbt run → dbt test → publish Gold` sequence.
- [ ] Task dependencies do not contain cycles.
- [ ] Task names are meaningful and reflect pipeline steps.
- [ ] DAG is readable by a new reviewer.
- [ ] Failure handling does not leave output state ambiguous.

### 9.6 RFM scoring

- [ ] Recency, Frequency, Monetary are computed as defined.
- [ ] Quintile scoring rules are documented and applied.
- [ ] Segment labels (Champions, Loyal, At Risk, Lost) are mapped correctly.
- [ ] Edge cases are handled or clearly noted.
- [ ] Total revenue in RFM reconciles with raw revenue within acceptable tolerance.

### 9.7 Validation logs and acceptance

- [ ] Row counts are checked across layers.
- [ ] Null / duplicate checks have clear results.
- [ ] FK integrity passes.
- [ ] Segment totals sum to the customer base.
- [ ] Issues are logged and re-checked after fixes.

### 9.8 Definition of Done for Sprint 2

- [ ] End-to-end path from CSV to Star Schema and RFM Table is working.
- [ ] Data validation evidence is available.
- [ ] DAG is scheduled or at least runnable with correct dependencies.
- [ ] Demo: `CSV → Airflow → dbt → Star Schema → RFM` is reproducible.
- [ ] No open High / Critical defects remain.

---

## 10. QA Checklist — Sprint 3

### 10.1 Feature engineering

- [ ] All 32 features are present in `mart_features` with correct column names.
- [ ] Feature value ranges are within expected bounds (validated by `assert_features_value_ranges`).
- [ ] No nulls in key feature columns.
- [ ] `is_one_time_buyer` and `is_uk` flags are binary (0/1).
- [ ] `cancellation_rate` is between 0 and 1.

### 10.2 Churn model

- [ ] XGBoost Pipeline (imputer + model) trains without errors.
- [ ] AUC on test set exceeds 0.80 (gate enforced in `ml/churn/uat.py`).
- [ ] `churn_probability` values are between 0 and 1.
- [ ] `churn_flag` is binary (0/1).
- [ ] `risk_tier` values are one of: High, Medium, Low.
- [ ] Model and metadata are saved to `ml/artifacts/`.

### 10.3 MLflow tracking

- [ ] Each training run is logged with parameters, metrics, and artifacts.
- [ ] Model is registered in MLflow model registry.
- [ ] Run ID is stored in `metadata.json` for traceability.

### 10.4 Batch scoring

- [ ] `mart_churn_scores` contains one row per customer.
- [ ] Customer count in `mart_churn_scores` matches `mart_rfm`.
- [ ] Airflow DAG `train → score → publish` completes end-to-end without failure.

### 10.5 Definition of Done for Sprint 3

- [ ] AUC gate passed.
- [ ] `mart_churn_scores` written to Gold layer.
- [ ] MLflow experiment accessible.
- [ ] No open High / Critical defects remain.

---

## 11. QA Checklist — Sprint 4

### 11.1 Clustering

- [ ] K-Means model trains on `mart_features` without errors.
- [ ] 3 clusters are produced with meaningful labels (High-Value, Mid-Tier, Occasional).
- [ ] Cluster profiles saved to `ml/artifacts/clustering/cluster_profiles.csv`.
- [ ] SHAP values computed and saved to `ml/artifacts/shap/`.

### 11.2 Streamlit app

- [ ] App starts without import errors.
- [ ] Churn tab: customer search, risk tier display, SHAP chart load correctly.
- [ ] Clustering tab: cluster profiles and customer assignments display correctly.
- [ ] Monitoring tab: drift metrics chart renders without errors.
- [ ] App loads `app/data/customers.parquet` and `app/model/model.pkl` correctly.

### 11.3 HuggingFace Spaces deployment

- [ ] App is publicly accessible without login.
- [ ] All tabs functional on the deployed version.
- [ ] No hardcoded local paths in app code.

### 11.4 GitHub Actions CI/CD

- [ ] `ruff` lint passes on all Python files.
- [ ] `dbt test` passes (35/35 assertions).
- [ ] `pytest` passes all unit and integration tests.
- [ ] Docker build completes without errors.
- [ ] CI pipeline is green on `main` branch.

### 11.5 Dashboard UAT

- [ ] Net Revenue in Fabric matches `SUM(net_revenue)` from `mart_kpi_monthly`.
- [ ] Total Orders matches `SUM(orders)` from `mart_kpi_monthly`.
- [ ] Active Customers = `DISTINCTCOUNT(fact_transactions[customer_sk])`.
- [ ] AOV = `SUM(revenue) / SUM(orders)` — verified against `mart_kpi_monthly`.
- [ ] Churn Risk Tier donut counts match `mart_churn_scores` by `risk_tier`.
- [ ] RFM Segment donut counts match `mart_rfm` by `segment`.
- [ ] All 8 CSV files exported to `data/fabric/` without errors.

### 11.6 Definition of Done for Sprint 4

- [ ] Dashboard published and accessible to team.
- [ ] CI/CD pipeline green on main.
- [ ] Streamlit app live on HuggingFace Spaces.
- [ ] Technical Report completed.
- [ ] Release tag `v1.0` created.
- [ ] All Jira tickets closed.
- [ ] No open High / Critical defects remain.

---

## 12. Deliverables Review Checklist

### 10.1 Document deliverables

- [ ] Document names are correct and consistent.
- [ ] Content aligns with overall objectives.
- [ ] Terms like BRD, UML, RFM, Gold, dbt are used consistently.

### 10.2 Code / pipeline deliverables

- [ ] Naming conventions are consistent.
- [ ] The stack is runnable without unclear manual steps.
- [ ] Data processing logic can be traced from input to output.
- [ ] Tests are placed close to the code they validate.

### 10.3 Output deliverables

- [ ] Outputs are in the expected formats.
- [ ] Numbers can be reconciled.
- [ ] Presentation does not hide logical errors.
- [ ] Sufficient evidence exists for pass / fail decisions.

---

## 11. Issue Template

When logging an issue, QA should use the following format:

- Where is the issue: file, section, task, or output.
- Impact: requirement violation, logic error, hard-to-review, or demo blocker.
- Suggested fix: specific changes required to meet the standard.
- Priority: Critical / High / Medium / Low.
- Re-check status: pending / passed / failed.

---

## 12. Handover to Sprint 3 (QA)

At the end of Sprint 2 QA must deliver at minimum:

- list of resolved and open issues;
- validation logs for Bronze / Silver / Gold / RFM;
- summary of remaining technical risks;
- notes for areas to watch when expanding to KPI marts and ML.

---

## 16. Conclusion

This test plan covers all four sprints of the Retail Customer Intelligence Platform project. Sprint 1–2 focused on requirements alignment and data pipeline correctness. Sprint 3 extended coverage to ML pipeline validation and model quality gates. Sprint 4 completed UAT on the dashboard, CI/CD green-light verification, and final release readiness.

All acceptance criteria were met and the project was released as `v1.0` on 30 June 2026.
