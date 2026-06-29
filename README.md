# Retail Customer Intelligence Platform

> **Mini Enterprise Data Platform — SDLC-complete.** A business-driven, full-lifecycle data platform that turns raw e-commerce transactions into customer segments, churn predictions, and an exportable retention list — delivered the way a real enterprise project flows: **BRD → UML → Star Schema → Airflow → dbt → Testing → CI/CD**.

<p align="left">
  <img alt="Airflow"   src="https://img.shields.io/badge/Airflow-orchestration-017CEE">
  <img alt="dbt"       src="https://img.shields.io/badge/dbt-transform-FF694B">
  <img alt="DuckDB"    src="https://img.shields.io/badge/DuckDB-engine-FFF000">
  <img alt="MLflow"    src="https://img.shields.io/badge/MLflow-tracking-0194E2">
  <img alt="Power BI"  src="https://img.shields.io/badge/Power%20BI-dashboard-F2C811">
  <img alt="Streamlit" src="https://img.shields.io/badge/Streamlit-HF%20Spaces-FF4B4B">
  <img alt="Docker"    src="https://img.shields.io/badge/Docker-compose-2496ED">
  <img alt="CI"        src="https://img.shields.io/badge/GitHub%20Actions-CI%2FCD-2088FF">
</p>

`AIO Conquer 2026 · Module 01 · Project #22 + #20`

---

## 1. Business Problem

Marketing sends **mass campaigns** to the entire customer base — low relevance, wasted spend. Retention is low and **high-value customers churn unnoticed**, with no systematic way to know who is about to leave.

**Objectives (measurable):**

| Goal | Target | Metric |
|---|---|---|
| Reduce churn | −10% | Churn rate (rolling 90-day) |
| Grow retention revenue | +5% | Revenue from returning customers |
| Campaign efficiency | Targeted, not mass | % campaigns sent to defined segments |

**Scope:** historical transactions → RFM segments → churn predictions → retention-list export + dashboard.
**Out of scope:** live campaign execution, email sending, real CRM integration (simulated).

> **Guiding principle — SDLC over model.** What makes a reviewer call this "enterprise" is the chain `BRD → UML → Star Schema → Airflow → dbt → Testing → CI/CD`, **not** the churn model (~15–20% of total value). Deliberately **no Kafka / Spark / Kubernetes / microservices** — maturity is shown through SDLC completeness, not framework count.

---

## 2. Architecture

### Medallion data flow

```
BRONZE          SILVER              GOLD                  ANALYTICS       ML
Raw load   →    Clean · dedup  →    Star schema      →    KPI marts  →    Churn · K-Means
(immutable)     date-shift          + RFM + features       Power BI        predictions
                                    + KPIs                               monitoring
```

### Dimensional model (Kimball star schema)

```
                  ┌────────────────────┐
   dim_customer ──┤  fact_transactions │── dim_product
   dim_date     ──┤  (qty · unit_price │── dim_country
                  │   · line_amount)   │
                  └────────────────────┘
                         │
            ┌────────────┼─────────────┐
         mart_rfm   mart_features  mart_kpi_monthly
         mart_churn_scores         mart_customer_clusters
```

---

## 3. Tech Stack

| Layer | Tool | Responsibility |
|---|---|---|
| Orchestration | **Apache Airflow 2.9** | ingest → clean → dbt run/test → train → score → publish → monitor |
| Storage | **Parquet + DuckDB** | Medallion lake (Bronze/Silver/Gold) + serving marts |
| Transform | **dbt-duckdb 1.8** | staging → intermediate → marts (star schema + RFM + KPIs + features) |
| ML tracking | **MLflow 2.11** | experiment tracking, model registry, artifact storage |
| ML models | **XGBoost + scikit-learn** | churn pipeline; **K-Means** for behavioural clustering |
| Explainability | **SHAP** | global + local feature importance |
| Serving | **Power BI** (primary BI) + **Streamlit** (ML demo on HF Spaces) | segments · KPIs · churn-risk · retention export |
| Containerization | **Docker Compose** | one-command reproducible local stack |
| CI/CD | **GitHub Actions** | lint (ruff) → pytest → dbt compile → docker build |

---

## 4. Repository Structure

```
.
├── .github/
│   └── workflows/
│       └── ci.yml              # CI: lint → pytest → dbt compile → docker build
│
├── airflow/
│   └── dags/
│       └── retail_pipeline_dag.py  # full end-to-end + monitoring DAG
│
├── app/                        # ── HuggingFace Spaces (self-contained) ──
│   ├── app.py                  # Streamlit: 6 tabs (Overview · Score · Retention · What-if · Clustering · Monitoring)
│   ├── Dockerfile              # Docker SDK, port 7860
│   ├── requirements.txt        # runtime deps only
│   ├── model/
│   │   ├── model.pkl           # sklearn Pipeline (imputer + XGBoost)
│   │   └── metadata.json       # threshold · feature list · score summary
│   └── data/
│       ├── customers.parquet   # 5,860 scored customers (churn prob + cluster)
│       ├── cluster_profiles.parquet  # 4-cluster K-Means profiles
│       └── monitoring.parquet  # model + data drift metrics
│
├── dashboard/
│   ├── Report_retail_customer_intelligence.pbix  # Fabric report file
│   └── semantic_model.pbix                       # Fabric semantic model
│
├── dbt/
│   ├── models/
│   │   ├── staging/            # stg_transactions · stg_calendar
│   │   ├── intermediate/       # int_transactions_cleaned
│   │   └── marts/              # dim_* · fact_transactions · mart_rfm
│   │                           # mart_features · mart_kpi_monthly · mart_churn_scores
│   ├── tests/                  # 35 custom SQL assertion tests
│   ├── dbt_project.yml
│   └── profiles.yml            # dev (relative path) + prod (Airflow absolute path)
│
├── ml/
│   ├── churn/                  # pipeline · train · evaluate · score · explain (SHAP) · uat
│   ├── clustering/             # pipeline · train · preprocessing · profile · evaluate
│   ├── monitoring/             # drift detection · monitoring store · pipeline
│   ├── artifacts/              # saved model artifacts (model.joblib · metadata.json · SHAP)
│   ├── config.py               # shared constants (paths · feature columns · thresholds)
│   ├── features.py             # feature matrix builder (reads from DuckDB mart_features)
│   ├── artifacts.py            # save/load helpers for model artifacts
│   └── validation.py           # model quality gate (AUC threshold check)
│
├── src/
│   ├── etl/
│   │   ├── bronze_ingest.py    # raw CSV → partitioned Parquet (immutable, date-rebased)
│   │   ├── silver_transform.py # clean · dedup · type-cast · validate → Silver
│   │   └── gold_build.py       # star schema + RFM → Parquet (reference impl; dbt is canonical)
│   └── utils/
│       ├── data_quality_check.py  # per-column quality checks (null rate, range, format)
│       └── layer_validation.py    # cross-layer reconciliation (row counts, revenue totals)
│
├── scripts/
│   ├── export_serving_app.py   # bundle model + customers + clusters + monitoring → app/
│   ├── export_powerbi.py       # export Gold marts → Parquet (Power BI) or CSV (Microsoft Fabric)
│   └── dbt_test.sh             # convenience wrapper: dbt run + dbt test
│
├── tests/
│   ├── conftest.py             # shared fixtures (bronze_like_df, silver_like_df)
│   ├── bronze/                 # ingest · partitioning · audit log
│   ├── silver/                 # transform · data quality utils
│   ├── gold/                   # star schema build · RFM mart
│   ├── cross_layer/            # Bronze→Silver→Gold reconciliation (integration)
│   └── ml/                     # model validation · churn UAT · AUC gate
│
├── notebooks/
│   ├── 01_eda_bronze.ipynb     # raw data profiling
│   ├── 02_eda_silver.ipynb     # cleaned data analysis
│   ├── 03_eda_gold.ipynb       # star schema + RFM exploration
│   ├── 04_sql_exploration.ipynb # DuckDB SQL queries on Gold layer
│   └── 05_churn_modeling.ipynb # model training walkthrough
│
├── docs/
│   ├── brd/                    # BRD.md · BRD.pdf
│   ├── architect/              # solution_architect.png · data_flow.png
│   ├── data_modeling/          # pipeline_design.md · source_to_target_mapping.md
│   ├── ml_document/            # ml_design.md
│   ├── planning/               # Project_Plan.md
│   ├── test/                   # test_plan.md · definition_of_done.md
│   ├── naming_convention/      # CONVENTIONS.md
│   ├── jira/                   # Jira_Plan_ACM1.pdf
│   └── meeting_minutes/        # sprint_1.md · sprint_2.md · sprint_3.md
│
├── data/                       # local lake (gitignored except .gitkeep)
│   ├── raw/                    # online_retail_listing.csv (place here — not committed)
│   ├── bronze/                 # partitioned Parquet (year_month=YYYY-MM/)
│   ├── silver/                 # cleaned Parquet + quality_report.json per partition
│   ├── gold/                   # mart outputs (mart_churn_scores · mart_monitoring · clustering/)
│   └── retail.duckdb           # DuckDB serving database (dbt target)
│
├── Makefile                    # make setup · make pipeline · make train · make serve …
├── CONTRIBUTING.md             # role assignments · branch conventions · PR process
├── pyproject.toml              # ruff config + pytest markers
├── docker-compose.yml          # Airflow + MLflow + Streamlit (ops dashboard)
├── Dockerfile.airflow
├── Dockerfile.mlflow
├── Dockerfile.streamlit        # runs dashboard/app.py on port 8501
├── requirements.txt            # full dev dependencies
└── .env.example                # environment variable template
```

---

## 5. Quickstart

### Option A — Make (recommended for local dev)

```bash
git clone https://github.com/AIVIETNAM-AIO-PhanVanTien/retail-customer-intelligence-platform.git
cd retail-customer-intelligence-platform

cp .env.example .env       # configure paths / credentials

make setup                 # install all dependencies
make pipeline              # bronze → silver → gold → dbt run/test
make train                 # train XGBoost churn model
make cluster               # run K-Means clustering
make export-app            # bundle model + data → app/
make serve                 # Streamlit demo on http://localhost:8501
```

Run `make help` to see all available commands.

### Option B — Docker Compose (full stack)

```bash
cp .env.example .env
docker compose up --build -d
```

| Service | URL |
|---|---|
| Airflow UI | http://localhost:8080 |
| MLflow UI | http://localhost:5001 |
| Streamlit Ops | http://localhost:8501 |

> **Dataset:** place `online_retail_listing.csv` under `data/raw/` (semicolon-delimited, Latin-1, ~1.05M rows, 2009–2011). Not committed — see `.gitignore`.

> **Primary BI dashboard is Power BI** — open `data/powerbi/*.pbix` in Power BI Desktop after running `make pipeline` + `python scripts/export_powerbi.py`.

> **Public ML demo** → [HuggingFace Spaces — retail-customer-intelligence](https://huggingface.co/spaces/tieensbeos/retail-customer-intelligence) (copy `app/` folder contents to a Docker Space).

---

## 6. End-to-End Pipeline

```
Raw CSV → Bronze (immutable) → Silver (clean) → Gold (star schema + RFM)
        → dbt marts (features · KPIs · churn scores)
        → ML (XGBoost churn · K-Means clusters · SHAP explanations)
        → Serving (Power BI · Streamlit · retention CSV export)
        → Monitoring (model drift · data drift → mart_monitoring)
```

### Key Gold marts

| Mart | Rows | Description |
|---|---|---|
| `fact_transactions` | ~980K | Line-level sales after cleaning |
| `dim_customer` | 5,860 | Identified customers only |
| `mart_rfm` | 5,860 | RFM quintiles + 10 segment labels |
| `mart_features` | 5,860 | 32 engineered features for ML |
| `mart_kpi_monthly` | 25 | Monthly revenue, retention, cohort metrics |
| `mart_churn_scores` | 5,860 | `churn_probability` + `churn_flag` |
| `mart_customer_clusters` | 5,860 | K-Means `cluster_id` + `cluster_name` |

---

## 7. ML Layer

### Churn model

- **Algorithm:** XGBoost (sklearn Pipeline: SimpleImputer → XGBoostClassifier)
- **Features:** 32 engineered from RFM + behavioural + trend signals
- **Threshold:** 0.5 default (adjustable in Streamlit sidebar)
- **Risk tiers:** High ≥ 0.7 · Medium ≥ 0.4 · Low < 0.4
- **Tracking:** MLflow experiment `churn-prediction`, model registry

### K-Means clustering (4 clusters)

| Cluster | Size | Recency | Frequency | Monetary |
|---|---|---|---|---|
| High-Value Active | 2,005 (34%) | 28 days | 12.6 orders | £6,514 |
| Average Regulars | 1,834 (31%) | 294 days | 4.6 orders | £1,634 |
| Dormant | 1,257 (22%) | 438 days | 1.0 orders | £335 |
| New / One-Time Buyers | 764 (13%) | 33 days | 2.0 orders | £673 |

### SHAP — top churn drivers

Global feature importance tracked in `ml/artifacts/shap/` and visualised in Streamlit tab **Score a customer**.

---

## 8. Streamlit Demo (HuggingFace Spaces)

6-tab interactive ML serving app — **no dbt / Airflow / MLflow needed at runtime**:

| Tab | What it does |
|---|---|
| 📊 Overview | Churn KPIs · score distribution · RFM segment table |
| 🔎 Score a customer | Churn probability · risk tier · SHAP drivers · customer snapshot |
| 📋 Retention list | Filter by risk tier / RFM segment / monetary · export CSV |
| 🧪 What-if | Adjust feature levers on a synthetic customer and re-score live |
| 🔵 Clustering | 4 cluster profiles · distribution · churn rate per cluster · customer list |
| 📈 Monitoring | Score distribution · risk tier breakdown · data drift status |

**Deploy:** copy contents of `app/` to a HuggingFace Docker Space root → push → done.

---

## 9. Testing Strategy

| Layer | Tool | What's tested |
|---|---|---|
| **Data quality** | dbt tests (35 SQL assertions) | unique · not_null · accepted_values · FK integrity · value ranges |
| **Pipeline unit** | pytest (`tests/bronze/` · `tests/silver/` · `tests/gold/`) | transform logic · date-shift · quality check utils |
| **Cross-layer** | pytest `tests/cross_layer/` (integration) | Bronze→Silver→Gold row reconciliation |
| **ML** | pytest `tests/ml/` | feature schema · value ranges · AUC gate · UAT scoring rules |

Run all unit tests: `make test` · Run all including integration: `make test-all`

---

## 10. CI/CD (GitHub Actions)

`.github/workflows/ci.yml` — triggers on every push and PR to `main`:

```
lint (ruff)
  ├── pytest          (unit tests, skip @integration)
  │     └── docker-build   (build app/Dockerfile — HF Spaces image)
  └── dbt-compile     (dbt parse — validates SQL + YAML without data)
```

---

## 11. Monitoring & Observability

Each Airflow pipeline run logs metrics to `data/gold/mart_monitoring/mart_monitoring.parquet`:

| Category | Metrics |
|---|---|
| `model_drift` | score_mean · score_std · score_p25/p50/p75/p90 · n_high/medium/low_risk · pct_high_risk · score_distribution_z |
| `data_drift` | n_features_checked · n_features_drifted · drift_rate (z-score based, threshold \|z\| > 3) |

Visible in the **📈 Monitoring** tab of the Streamlit app and the local ops dashboard (`dashboard/app.py`).

---

## 12. Document Map

| Document | Location | Description |
|---|---|---|
| Business Requirements (BRD) | [docs/brd/BRD.md](docs/brd/BRD.md) | Pain points · objectives · stakeholders · scope · FR/NFR |
| Solution Architecture | [docs/architect/](docs/architect/) | Architecture diagram · data flow |
| Pipeline Design | [docs/data_modeling/pipeline_design.md](docs/data_modeling/pipeline_design.md) | Medallion layer design · dbt model map |
| Source-to-Target Mapping | [docs/data_modeling/source_to_target_mapping.md](docs/data_modeling/source_to_target_mapping.md) | Column-level lineage |
| ML Design | [docs/ml_document/ml_design.md](docs/ml_document/ml_design.md) | Churn label logic · feature plan · model selection |
| Project Plan | [docs/planning/Project_Plan.md](docs/planning/Project_Plan.md) | Sprint timeline · ownership matrix · milestones |
| Test Plan | [docs/test/test_plan.md](docs/test/test_plan.md) | Test strategy · acceptance criteria |
| Definition of Done | [docs/test/definition_of_done.md](docs/test/definition_of_done.md) | DoD per sprint |
| Naming Conventions | [docs/naming_convention/CONVENTIONS.md](docs/naming_convention/CONVENTIONS.md) | Branch · file · variable naming rules |
| Meeting Minutes S1 | [docs/meeting_minutes/sprint_1.md](docs/meeting_minutes/sprint_1.md) | Kickoff · architecture decisions · role assignments |
| Meeting Minutes S2 | [docs/meeting_minutes/sprint_2.md](docs/meeting_minutes/sprint_2.md) | Data pipeline decisions · issues resolved |
| Meeting Minutes S3 | [docs/meeting_minutes/sprint_3.md](docs/meeting_minutes/sprint_3.md) | ML decisions · threshold · feature store |
| Meeting Minutes S4 | [docs/meeting_minutes/sprint_4.md](docs/meeting_minutes/sprint_4.md) | Final delivery · dashboard · CI/CD · retrospective |
| Contributing Guide | [CONTRIBUTING.md](CONTRIBUTING.md) | Role ownership · branch conventions · PR process · local setup |

---

## 13. Delivery Status

| Component | Owner | Status |
|---|---|---|
| BRD + UML + Architecture | Tech Lead | ✅ Done |
| Bronze / Silver / Gold ETL | Data | ✅ Done |
| dbt models + 25 data tests | Pipeline | ✅ Done |
| Airflow DAG (full pipeline) | Pipeline | ✅ Done |
| RFM scoring + 10 segments | Model | ✅ Done |
| Churn model (XGBoost) + SHAP | Model | ✅ Done |
| K-Means clustering (4 clusters) | Model | ✅ Done |
| MLflow tracking + registry | Pipeline | ✅ Done |
| Monitoring (data + model drift) | Pipeline | ✅ Done |
| Streamlit demo (HF Spaces, 6 tabs) | Pipeline | ✅ Done |
| GitHub Actions CI/CD | Pipeline | ✅ Done |
| Docker Compose full stack | Pipeline | ✅ Done |
| pytest suite (unit + ML + integration) | QA | ✅ Done |
| Fabric dashboard (Business Performance + Customer Intelligence) | Data | ✅ Done |
| Business Impact Report | Tech Lead | ✅ Done |
| LaTeX Technical Report | All | ✅ Done |

---

## 14. Team

| Member | Role | Primary Scope |
|---|---|---|
| Võ Ngọc Gia Bảo | Team Leader · Data | Sprint planning · EDA · Star Schema · dbt models · KPI marts · Power BI · demo video |
| Phan Văn Tiến | Tech Lead | BRD · UML · architecture · MLflow strategy · business impact · PR reviews · slides |
| Phúc Nhân Nguyễn | AI Eng · Model | RFM scoring · feature engineering · churn model · SHAP · K-Means |
| Ngọc Phương | AI Eng · Pipeline | Repo · Docker · Airflow DAGs · dbt project · MLflow server · CI/CD · monitoring |
| Hoàng Đức Kiên | QA · Reviewer | DoD · test plan · data/model/UAT validation · final QA report |

> See [CONTRIBUTING.md](CONTRIBUTING.md) for branch conventions, PR process, and sprint ownership matrix.

---

## License

Dataset: [Online Retail Listing](https://www.kaggle.com/datasets/ilkeryildiz/online-retail-listing) (public, Kaggle). Project code: [MIT](LICENSE).
