# Project Plan & Team Charter

**Retail Customer Intelligence Platform** — a 4-week delivery of a Mini Enterprise Data Platform: Power BI Dashboard + RFM + Churn Prediction + CI/CD, built SDLC-first.

`AIO Conquer 2026 · Module 01 · Project #22 + #20`

- **Jira Project Key:** `ACM1`
- **Board:** https://vongocgiabao79.atlassian.net/jira/software/projects/ACM1
- **Timeline:** 05 Jun 2026 → 30 Jun 2026 · **Deadline: all completed before 01 Jul 2026**
- **Cadence:** 4 sprints · 5 members · 88 Jira tickets · **Weekly meeting every Thursday 22:00**

---

## 0. Sprint Goal & Guiding Principle

**Goal:** In 4 weeks, demo a Mini Enterprise Data Platform with dashboard + RFM + churn prediction + basic CI/CD. We do **not** attempt the full P0→P3 roadmap; we deliver a credible **vertical slice**.

> **SDLC over model.** Many teams jump straight into training XGBoost on day one. Here, what makes a reviewer call it "enterprise" is the chain **BRD → UML → Star Schema → Airflow → dbt → Testing → CI/CD** — not the churn model. The model is only ~15–20% of total project value. Resist the urge to over-invest in modelling early.

---

## 1. Team & Roles

| Jira Role Tag | Member | SDLC Role | Primary Scope |
| --- | --- | --- | --- |
| **TEAM LEADER / DATA** | Võ Ngọc Gia Bảo | Team Leader & AI Eng (Data) | Sprint planning · demos · EDA · Star Schema · dbt models¹ · Power BI · feature/KPI marts · demo video |
| **TECH LEAD** | Phan Văn Tiến | Tech Leader & Team Member | BRD · UML · architecture · MLflow² · business impact · **PR reviews** · presentation slides |
| **MODEL** | Phúc Nhân Nguyễn | AI Engineer (Model) | RFM scoring · feature engineering · churn model · batch scoring · SHAP · K-Means |
| **PIPELINE** | Ngọc Phương | AI Engineer (Pipeline) | Repo · Docker · Airflow DAGs · dbt models · MLflow server · CI/CD · monitoring |
| **QA** | Hoàng Đức Kiên | QA / Reviewer & Team Member | Definition of Done · test plans · data/model/UAT validation · final QA report |

> ¹ Gia Bảo owns the **Bronze→Silver→Gold** data layers and modeling; **Ngọc Phương** owns the **dbt project + models/tests** implementation (ACM1-33/34). They collaborate on the Gold marts.
> ² **MLflow:** Tech Lead owns the experiment/registry strategy; **Pipeline** stands up and runs the tracking server (ACM1-58).

---

## 2. Sprint Timeline

### Sprint 1 — Discovery & Onboarding · 05–11 Jun · *lay the SDLC foundation*

| Owner | Tasks | Deliverables |
| --- | --- | --- |
| ALL | Read Git/Jira docs, study assigned role (by 07 Jun) | Onboarding complete |
| TEAM LEADER | Kickoff (topic, scope, team charter, risk register) · Sprint 1 planning | Charter · backlog |
| TECH LEAD | BRD (pain points, objectives, stakeholders, scope) · UML (Use Case / Activity / Sequence) · Solution Architecture + data-flow | `docs/BRD.md`, `docs/Solution_Architecture.md` |
| DATA | Data profiling & EDA on `online_retail_listing.csv` · Star Schema ERD + Data Dictionary | `notebooks/01_eda.ipynb`, `docs/data_dictionary.xlsx` |
| MODEL | Churn label logic · RFM segmentation approach · target metrics · ML Design Doc | `docs/ml_design.md` |
| PIPELINE | Repo setup (branches, `.gitignore`, folder structure, conventions) · Docker Compose skeleton (Airflow, dbt, DuckDB, MLflow) | `docker-compose.yml`, repo skeleton |
| QA | Definition of Done (all 4 sprints) · Test Plan & checklist · review BRD/UML/Star Schema for early risks | `docs/test_plan.md` |

> **Sprint 1 Demo (Thu 11 Jun):** BRD + UML + Star Schema + EDA + ML Design + Repo + Docker skeleton

### Sprint 2 — Data Platform MVP · 12–18 Jun · *raw → star schema → RFM*

| Owner | Tasks | Output |
| --- | --- | --- |
| DATA | Bronze (ingest CSV → Parquet + schema enforcement + audit log) · Silver (clean, dedup, date-shift, validate) · Gold star schema · RFM mart | `dim_customer`, `dim_product`, `dim_date`, `dim_country`, `fact_transactions`, RFM mart |
| PIPELINE | dbt project (`dbt_project.yml`, `profiles.yml`, staging→intermediate→marts) · dbt tests · Airflow DAG `ingest → clean → dbt run → dbt test → publish Gold` | Working scheduled DAG + dbt models |
| MODEL | RFM scoring logic (quintile calc, segment mapping, edge cases) · exploratory RFM analysis (segment distribution, revenue contribution) | Segment labels (Champions / Loyal / At Risk / Lost) |
| QA | Validate Bronze/Silver/Gold (row counts, nulls, dups) · RFM totals reconcile with raw revenue · star schema FK integrity · accepted segment labels | Validation log |
| TECH LEAD | Review PRs for data pipeline + dbt models + star schema | PR approvals |

> **Sprint 2 Demo (Thu 18 Jun):** `CSV → Airflow → dbt → Star Schema → RFM Table` (end-to-end data pipeline)

### Sprint 3 — ML Layer & Analytics · 19–25 Jun · *features → model → churn probability*

| Owner | Tasks | Output |
| --- | --- | --- |
| DATA | Feature mart (`AOV`, `LTV`, `tenure`, `order_gap`, `avg_basket_size`) · KPI marts (revenue by month, retention, cohort, segment distribution) · Power BI layout design | `mart_customer_features`, KPI marts |
| MODEL | Feature engineering (R, F, M, AOV, LTV, tenure, order patterns) · train LR + XGBoost (cross-validation) · evaluation (AUC, precision, recall, F1, confusion matrix, threshold) · batch scoring (`churn_probability` + `churn_flag`) | Trained models + metrics |
| PIPELINE | Extend Airflow DAG (`train_model → score_customers → publish predictions`) · MLflow tracking server + experiment logging + model registry | Extended DAG + MLflow server |
| QA | Model validation (feature schema, value ranges, AUC gate **> 0.80**) · data-quality tests on feature/KPI marts | Model test report |
| TECH LEAD | Review PRs for ML pipeline, feature engineering, MLflow integration | PR approvals |

> **Sprint 3 Demo (Thu 25 Jun):** `Customer → Features → Churn Model → Churn Probability` (ML pipeline)

### Sprint 4 — Dashboard, CI/CD & Final Delivery · 26–30 Jun · *ship it*

| Owner | Tasks | Output |
| --- | --- | --- |
| DATA | Power BI dashboard (RFM segments, revenue KPIs, churn-risk view, cohort heatmap) · cohort + retention curves | Power BI dashboard |
| MODEL | Feature importance / **SHAP** (top churn drivers) · **K-Means** clustering (behavior-based segmentation) | Explainability + clusters |
| PIPELINE | GitHub Actions CI (`lint → dbt test → pytest → docker build`) · finalize Docker Compose + Streamlit demo app · monitoring (data + model drift → monitoring table + Ops tab) | `.github/workflows/ci.yml`, monitoring |
| QA | UAT (Power BI numbers match Gold tables, segment counts, churn/retention export) · final QA report (coverage, known issues, sign-off) | UAT sign-off |
| TECH LEAD | Business Impact Report (segment revenue, recommendations, ROI) · finalize codebase + **tag release `v1.0`** · presentation slides + demo script | `docs/business_impact.md`, `v1.0` |
| ALL | LaTeX Technical Report (4 sections by role — see §7) | Technical report |
| TEAM LEADER | Record demo video (end-to-end walkthrough) · final review + retrospective | Demo video |

> **Final Delivery (Tue 30 Jun):** `BRD → Pipeline → Star Schema → RFM → ML → Power BI → CI/CD` + LaTeX Report + Demo Video

---

## 3. Component Ownership Matrix

| Component | Owner (Role) | Sprint |
| --- | --- | --- |
| BRD + UML Diagrams | Phan Văn Tiến (TECH LEAD) | S1 |
| Solution Architecture | Phan Văn Tiến (TECH LEAD) | S1 |
| Data Profiling & EDA | Võ Ngọc Gia Bảo (DATA) | S1 |
| Star Schema ERD + Data Dictionary | Võ Ngọc Gia Bảo (DATA) | S1 |
| ML Design Document | Phúc Nhân Nguyễn (MODEL) | S1 |
| GitHub Repo + Conventions | Ngọc Phương (PIPELINE) | S1 |
| Docker Compose Skeleton | Ngọc Phương (PIPELINE) | S1 |
| Definition of Done + Test Plan | Hoàng Đức Kiên (QA) | S1 |
| Bronze / Silver / Gold Pipeline | Võ Ngọc Gia Bảo (DATA) | S2 |
| dbt Models + Tests | Ngọc Phương (PIPELINE) | S2 |
| Airflow DAG (data pipeline) | Ngọc Phương (PIPELINE) | S2 |
| RFM Scoring + Segmentation | Phúc Nhân Nguyễn (MODEL) | S2 |
| Data Validation (layers + RFM) | Hoàng Đức Kiên (QA) | S2 |
| Feature Mart + KPI Marts | Võ Ngọc Gia Bảo (DATA) | S3 |
| Churn Model (LR + XGBoost) | Phúc Nhân Nguyễn (MODEL) | S3 |
| Batch Scoring Pipeline | Phúc Nhân Nguyễn (MODEL) | S3 |
| MLflow Tracking + Registry | Ngọc Phương (PIPELINE) | S3 |
| Airflow DAG (ML extension) | Ngọc Phương (PIPELINE) | S3 |
| Model + Feature Validation | Hoàng Đức Kiên (QA) | S3 |
| Power BI Dashboard | Võ Ngọc Gia Bảo (DATA) | S4 |
| Cohort + Retention Visualizations | Võ Ngọc Gia Bảo (DATA) | S4 |
| SHAP + Feature Explainability | Phúc Nhân Nguyễn (MODEL) | S4 |
| K-Means Clustering | Phúc Nhân Nguyễn (MODEL) | S4 |
| GitHub Actions CI/CD | Ngọc Phương (PIPELINE) | S4 |
| Docker Finalize + Streamlit | Ngọc Phương (PIPELINE) | S4 |
| Data + Model Monitoring | Ngọc Phương (PIPELINE) | S4 |
| UAT + Final QA Report | Hoàng Đức Kiên (QA) | S4 |
| Business Impact Report | Phan Văn Tiến (TECH LEAD) | S4 |
| LaTeX Technical Report (4 sections) | All members (by role) | S4 |
| Presentation Slides + Demo Script | Phan Văn Tiến (TECH LEAD) | S4 |
| Demo Video | Võ Ngọc Gia Bảo (TEAM LEADER) | S4 |

---

## 4. Build Priority — Path to 10/10

If forced to cut scope, build in this order. The **first seven items** are what earn the "enterprise" judgment.

1. **BRD + UML** — the business framing that frames everything
2. **Star Schema** — dimensional model, the Data Engineer money-shot
3. **Airflow** — orchestration backbone
4. **dbt** — transforms + tests as code
5. **Dashboard (Power BI)** — the visible deliverable stakeholders see
6. **Docker** — `docker-compose up`, reproducible for reviewers
7. **Churn Model** — predictive layer (only now)
8. **MLflow** — experiment tracking + registry
9. **GitHub Actions** — CI/CD automation
10. **Monitoring + K-Means** — data + model observability + extra segmentation

---

## 5. MVP Architecture (4-Week Build)

```
BRONZE        SILVER        GOLD            ANALYTICS       ML
Raw CSV   →   Clean    →    Star schema →   KPI marts   →   Churn · K-Means
ingest        validate      + RFM           Power BI        scoring
```

```
docker-compose up
┌──────────────────────────────────────────────────────┐
│  Airflow → dbt + DuckDB → Postgres (serving)          │
│     │                                                  │
│     └─▶ train + score ─▶ MLflow   └─▶ Streamlit demo   │
└──────────────────────────────────────────────────────┘
Power BI connects to serving marts · CI: GitHub Actions → lint · dbt test · pytest · docker build
```

Fully local/containerized for fast iteration and reviewer reproducibility within the 4-week window — no cloud provisioning overhead.

---

## 6. Key Milestones

| Date | Milestone | Expected deliverable |
| --- | --- | --- |
| 07 Jun | Onboarding complete | All 5 members finished Git/Jira docs + role study |
| 11 Jun (Thu) | Sprint 1 Demo | BRD + UML + Star Schema + EDA + ML Design + Repo + Docker skeleton |
| 18 Jun (Thu) | Sprint 2 Demo | `CSV → Airflow → dbt → Star Schema → RFM Table` |
| 25 Jun (Thu) | Sprint 3 Demo | `Customer → Features → Churn Model → Churn Probability` |
| 30 Jun (Tue) | **Final Delivery** | Full walkthrough + Power BI + CI/CD + LaTeX Report + Demo Video |

---

## 7. Final Deliverables (Sprint 4)

- **LaTeX Technical Report** (built with `AIConquer2026_Kit`) — 4 sections by role:
  - Data modeling, EDA, star schema, Power BI dashboard — *Data*
  - ML methodology, feature engineering, results, error analysis — *Model*
  - Pipeline design, dbt, Airflow, CI/CD, monitoring — *Pipeline*
  - System architecture, deployment, business impact — *Tech Lead*
- **Presentation slides + demo script** — Tech Lead
- **Demo video** (end-to-end walkthrough) — Team Leader
- **Business Impact Report** — Tech Lead
- **Final QA report** (sign-off) — QA
- **Release tag `v1.0`** on `main`

---

## 8. Appendix — Production Cloud Path (Azure)

Out of scope for the 4-week build; documented to show cloud vision. The local stack maps cleanly onto Azure-native managed services (no Databricks).

| Local (MVP) | Azure (production) | Note |
| --- | --- | --- |
| Airflow (Docker) | Azure Data Factory | Managed orchestration / scheduling |
| Local volume / DuckDB | ADLS Gen2 (Bronze/Silver/Gold) | Lakehouse storage |
| dbt + train (container) | Container Apps Job (cron) | Scale-to-zero, pay-per-run |
| Postgres (Docker) | Azure DB for PostgreSQL | Serving marts (+ pgvector) |
| Streamlit (Docker) | Container Apps (App) | Serverless dashboard hosting |
| `.env` file | Azure Key Vault | Secrets + Managed Identity |
| local images | Azure Container Registry | Image registry |
| logs to console | Azure Monitor + Log Analytics | Data/model monitoring + alerts |

Aligns with the Tech Lead's AZ-104 / DP-700 certification track — the same architecture doubles as a cloud-skills demonstration.
