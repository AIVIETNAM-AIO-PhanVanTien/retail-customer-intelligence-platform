# Retail Customer Intelligence Platform

> **Mini Enterprise Data Platform — SDLC-complete.** A business-driven, full-lifecycle data platform that turns raw e-commerce transactions into customer segments, churn predictions, and an exportable retention list — delivered the way a real enterprise project flows: **BRD → UML → Star Schema → Airflow → dbt → Testing → CI/CD**.

<p align="left">
  <img alt="Airflow"  src="https://img.shields.io/badge/Airflow-orchestration-017CEE">
  <img alt="dbt"      src="https://img.shields.io/badge/dbt-transform-FF694B">
  <img alt="DuckDB"   src="https://img.shields.io/badge/DuckDB-engine-FFF000">
  <img alt="MLflow"   src="https://img.shields.io/badge/MLflow-tracking-0194E2">
  <img alt="Power BI" src="https://img.shields.io/badge/Power%20BI-dashboard-F2C811">
  <img alt="Streamlit" src="https://img.shields.io/badge/Streamlit-demo-FF4B4B">
  <img alt="Docker"   src="https://img.shields.io/badge/Docker-compose-2496ED">
  <img alt="CI"       src="https://img.shields.io/badge/GitHub%20Actions-CI%2FCD-2088FF">
</p>

`AIO Conquer 2026 · Module 01 · Project #22 + #20`

---

## 1. The Business Problem (BRD)

Marketing sends **mass campaigns** to the entire customer base — low relevance, wasted spend. Retention is low and **high-value customers churn unnoticed**, with no systematic way to know who is about to leave.

**Objectives (measurable):**

| Goal | Target | Metric |
| --- | --- | --- |
| Reduce churn | −10% | Churn rate (rolling 90-day) |
| Grow retention revenue | +5% | Revenue from returning customers |
| Campaign efficiency | Targeted, not mass | % campaigns sent to defined segments |

**Scope:** historical transactions → RFM segments → churn predictions → retention-list export + dashboard.
**Out of scope:** live campaign execution, email sending, real CRM integration (simulated).
**Success:** dashboard delivers segment + churn view; retention list exportable; model AUC and data quality monitored.

> **Guiding principle — SDLC over model.** What makes a reviewer call this "enterprise" is the chain `BRD → UML → Star Schema → Airflow → dbt → Testing → CI/CD`, **not** the churn model (~15–20% of total value). We deliberately use **no Kafka / Spark / Kubernetes / microservices** — maturity is shown through SDLC completeness, not framework count.

---

## 2. Architecture

┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                      APACHE AIRFLOW                                         │
│          ingest → clean → dbt run → dbt test → train → score → publish                      │
└─────────────────────────────────────────────────────────────────────────────────────────────┘

                                         ORCHESTRATION

        │
        ▼

┌────────────────┐
│    SOURCE      │
├────────────────┤
│ Online Retail    │
│ List for RFM     │
│ ~1.01M rows      │
└────────────────┘
        │
        ▼

┌─────────────────────────────────────────────────────────────────────────────┐
│                     MEDALLION LAKEHOUSE (DuckDB + Parquet)                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  BRONZE                     SILVER                     GOLD                 │
│                                                                             │
│  Raw CSV                    Cleaned                    Star Schema          │
│  PyArrow                    Dedup                      + RFM Mart           │
│  Audit Log                  Date Shift                                      │
│  Immutable                  Validation                                      │
│                                                                             │
│                                                     ┌────────────────────┐  │
│                                                     │ fact_transactions  │  │
│                                                     └─────────┬──────────┘  │
│                                                               │             │
│                     ┌──────────────┬──────────────┬───────────┴──────────┐  │
│                     │              │              │                      │  │
│              dim_customer    dim_product     dim_date           dim_country │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

        │
        ▼

┌───────────────────────────────┐
│       dbt + DuckDB            │
├───────────────────────────────┤
│ staging                       │
│ intermediate                  │
│ marts                         │
│                               │
│ dbt Tests                     │
│ - unique                      │
│ - not_null                    │
│ - relationships               │
│ - accepted_values             │
│ - freshness                   │
└───────────────────────────────┘

        │
        ▼

┌─────────────────────────────────────────────────────────────┐
│                     MACHINE LEARNING                        │
├─────────────────────────────────────────────────────────────┤
│ Feature Engineering                                         │
│ - Recency                                                   │
│ - Frequency                                                 │
│ - Monetary                                                  │
│ - AOV                                                       │
│ - LTV                                                       │
│ - Tenure                                                    │
│                                                             │
│ Models                                                      │
│ - Logistic Regression                                       │
│ - XGBoost                                                   │
│                                                             │
│ Explainability                                              │
│ - SHAP                                                      │
│                                                             │
│ Segmentation                                                │
│ - K-Means                                                   │
│                                                             │
│ MLflow                                                      │
│ - Experiment Tracking                                       │
│ - Model Registry                                            │
│ - Batch Scoring                                             │
└─────────────────────────────────────────────────────────────┘

        │
        ▼

┌─────────────────────────────────────────────────────────────┐
│                         SERVING                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Power BI (Primary Dashboard)                                │
│ - Revenue KPIs                                              │
│ - RFM Segments                                              │
│ - Cohort Retention                                          │
│ - Churn Risk                                                │
│                                                             │
│ Streamlit Demo                                              │
│ - Segment Explorer                                          │
│ - Retention List Export                                     │
│ - Ops Dashboard                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════
CROSS-CUTTING
═══════════════════════════════════════════════════════════════════════════════

Docker Compose
    └─ Airflow
    └─ DuckDB
    └─ MLflow
    └─ Streamlit

GitHub Actions
    lint → dbt test → pytest → docker build

Monitoring
    Row Count
    Null %
    Freshness
    Feature Drift
    Model Drift
    AUC Monitoring

### Medallion data flow

```
BRONZE          SILVER              GOLD                ANALYTICS         ML
Raw load   →    Clean · dedup  →    Star schema    →    KPI marts    →    Churn · K-Means
(immutable)     date-shift          + RFM               dashboard         predictions
```

### Dimensional model (Kimball star schema)

```
                  ┌────────────────────┐
   dim_customer ──┤  fact_transactions │── dim_product
   dim_date     ──┤  (measures: qty,   │── dim_country
                  │   unit_price,      │
                  │   line_amount)     │
                  └────────────────────┘
```

`fact_transactions` holds the measures; the **RFM** and **churn** aggregates are derived Gold marts built on top.

---

## 3. Tech Stack

| Layer | Tool | Responsibility |
| --- | --- | --- |
| Orchestration | **Apache Airflow** | ingest → dbt run → dbt test → train → score → publish |
| Storage | **Delta Lake / Parquet** | ACID + immutable Bronze + time travel |
| Transform | **dbt + DuckDB** | staging → intermediate → marts (star schema + RFM) |
| ML & tracking | **XGBoost + MLflow** | training, experiments, registry, batch scoring |
| Serving | **Power BI** (primary) + **Streamlit** (demo app) | segments, KPIs, churn-risk, cohort, retention export |
| Containerization | **Docker Compose** | one-command reproducible stack |
| CI/CD | **GitHub Actions** | lint → dbt test → pytest → docker build |

---

## 4. Repository Structure

```
.
├── airflow/                 # DAGs: ingest → clean → dbt → train → score → publish
│   └── dags/
├── dbt/                     # staging → intermediate → marts (star schema + RFM)
│   ├── models/
│   │   ├── staging/
│   │   ├── intermediate/
│   │   └── marts/           # dim_*, fact_transactions, fct_rfm, mart_customer_features
│   └── schema.yml           # data-quality tests (unique, not_null, accepted_values, relationships)
├── ml/                      # feature engineering, churn model (LR + XGBoost), SHAP, K-Means
├── dashboard/               # Streamlit demo app (segments · KPIs · churn-risk · retention export)
├── powerbi/                 # Power BI report (.pbix) + data model — primary dashboard
├── data/                    # local volume (Bronze/Silver/Gold) — gitignored
├── notebooks/               # eda.ipynb, profiling
├── tests/                   # pytest: transform funcs, DAG integrity, date-shift logic
├── docs/                    # planning/ · naming_convention/ · jira/ · BRD.md ·
│                            # Solution_Architecture.md · ml_design.md · test_plan.md · business_impact.md
├── report/                  # LaTeX technical report (AIConquer2026_Kit, 4 sections)
├── .github/workflows/ci.yml # CI pipeline
├── docker-compose.yml       # Airflow + dbt/DuckDB + Postgres + MLflow + Streamlit
└── README.md
```

---

## 5. Quickstart

```bash
# 1. Clone
git clone <your-repo-url>.git
cd retail-customer-intelligence-platform

# 2. Configure
cp .env.example .env          # set credentials / paths

# 3. Run the whole stack — one command
docker-compose up
```

Then open:

| Service | URL |
| --- | --- |
| Streamlit demo app | http://localhost:8501 |
| Airflow UI | http://localhost:8080 |
| MLflow UI | http://localhost:5000 |

> The **primary dashboard is Power BI** (`powerbi/*.pbix`, opened in Power BI Desktop, connected to the serving marts). Streamlit is the lightweight in-stack demo.

> **Dataset:** "Online Retail List for RFM" (real, ~1.01M rows). Provided as `online_retail_listing.csv` — place under `data/raw/` (semicolon-delimited, comma decimals, `dd.mm.yyyy` dates). Timestamps are **date-rebased to the present** so recency and churn windows stay meaningful. The file is **not committed** (see `.gitignore`).

---

## 6. End-to-End Pipeline

```
Raw CSV → Airflow → dbt Star Schema → RFM → ML Churn → Dashboard → Retention List + Business Impact
```

1. **Ingest** transactions (Bronze, immutable)
2. **Clean & validate** → quality gate → quarantine + alert on failure
3. **Compute RFM** (Recency, Frequency, Monetary) → quintile scores → segment labels
4. **Predict churn** (batch score)
5. **Publish** to dashboard
6. **Export** retention list for Marketing

### RFM Gold mart (selected columns)

| Column | Type | Meaning |
| --- | --- | --- |
| `customer_id` | VARCHAR | Business key from source |
| `recency_days` | INT | Days since last purchase |
| `frequency` | INT | Distinct order count |
| `monetary` | FLOAT | Total spend (GBP) |
| `r_score` / `f_score` / `m_score` | INT (1–5) | Quintile scores |
| `segment` | VARCHAR | Champions, Loyal, At Risk, Lost, … |
| `churn_probability` | FLOAT | Model output 0–1 |
| `churn_flag` | BOOLEAN | Threshold-applied prediction |

---

## 7. Testing Strategy

Three layers, automated in CI:

- **Data quality (dbt):** `unique` · `not_null` · `accepted_values` (segment labels) · `relationships` (FK integrity) · freshness checks.
- **Pipeline unit tests (pytest):** transform functions · Airflow DAG integrity (no cycles, valid deps) · date-shift correctness.
- **ML tests:** feature validation (ranges, schema) · data-drift detection (train vs serve) · minimum-performance gate (AUC threshold).
- **Acceptance:** RFM totals reconcile with raw revenue · segment counts sum to customer base · dashboard numbers match Gold tables.

---

## 8. CI/CD (GitHub Actions)

```
push / pull_request
  → lint        (ruff / sqlfluff)
  → dbt test    (data quality on sample)
  → pytest      (unit + DAG integrity)
  → build image (docker build)
  → publish artifact
```

---

## 9. Monitoring & Observability

- **Data:** row count per run · null % per key column · ingestion freshness · schema-change alerts.
- **Model:** prediction distribution drift · AUC degradation over time · feature drift vs training baseline · scoring volume.

Lightweight implementation: metrics logged to a monitoring table each run + a small Streamlit "Ops" tab (Evidently optional for drift reports).

---

## 10. Business Impact (illustrative — real numbers produced at build time)

- **Champions** generate ~48% of total revenue from a small share of customers.
- **At Risk** customers account for ~22% of revenue — the priority retention target.
- The **top 5% churn-risk** customers represent ~18% of revenue at stake.

| Segment | Action | Expected outcome |
| --- | --- | --- |
| At Risk + high Monetary | Priority retention offer | Protect high-value revenue |
| Top churn-risk 5% | Personalised win-back campaign | Directly reduce churn rate |
| Champions | Loyalty / referral program | Maximise lifetime value |
| New customers | Onboarding nurture | Convert to repeat buyers |

---

## 11. Roadmap

| Phase | Scope | Priority |
| --- | --- | --- |
| **P0 · Discovery** | BRD + Use Case / Activity / Sequence + ERD + data dictionary | MUST |
| **P1 · MVP** | Ingest + date-shift → Medallion star schema → RFM Gold → Streamlit dashboard → Docker | MUST |
| **P2 · ML + Quality** | Churn model + MLflow + batch scoring + dbt/pytest tests + GitHub Actions | SHOULD |
| **P3 · Ops + Impact** | K-Means · monitoring (data + model drift) · business impact report · streaming replay | NICE |

See [docs/planning/Project_Plan.md](docs/planning/Project_Plan.md) for the 4-week sprint plan and [docs/naming_convention/CONVENTIONS.md](docs/naming_convention/CONVENTIONS.md) for naming & Git workflow. Jira board: [`ACM1`](https://vongocgiabao79.atlassian.net/jira/software/projects/ACM1).

---

## 12. Team

| Role | Member | Ownership |
| --- | --- | --- |
| **Team Leader · AI Eng (Data)** | Võ Ngọc Gia Bảo | Sprint planning · demos · EDA · Star Schema · feature/KPI marts · Power BI · demo video |
| **Tech Lead** | Phan Văn Tiến | BRD · UML · architecture · MLflow · business impact · PR reviews · slides |
| **AI Eng · Model** | Phúc Nhân Nguyễn | RFM scoring · feature engineering · churn model · SHAP · K-Means |
| **AI Eng · Pipeline** | Ngọc Phương | Repo · Docker · Airflow DAGs · dbt models · MLflow server · CI/CD · monitoring |
| **QA · Reviewer** | Hoàng Đức Kiên | DoD · test plan · data/model/UAT validation · final QA report |

---

## License

Dataset: Online Retail List for RFM. Project code: see `LICENSE`.