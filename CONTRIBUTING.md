# Contributing — Retail Customer Intelligence Platform

`AIO Conquer 2026 · Module 01 · Project #22 + #20`

---

## Team & Role Assignments

| GitHub Account | Member | Role | Primary Scope |
|---|---|---|---|
| AIVIETNAM-AIO-PhanVanTien | Phan Văn Tiến | **Tech Lead** | BRD · UML · Architecture · MLflow strategy · Business Impact Report · PR reviews · Slides |
| *(Gia Bảo)* | Võ Ngọc Gia Bảo | **Team Leader / Data** | EDA · Star Schema · dbt models · KPI marts · Power BI dashboard · Demo video |
| *(Phúc Nhân)* | Phúc Nhân Nguyễn | **Model** | RFM scoring · Feature engineering · Churn model · SHAP · K-Means clustering |
| *(Ngọc Phương)* | Ngọc Phương | **Pipeline** | Repo setup · Docker · Airflow DAGs · dbt project · MLflow server · CI/CD · Monitoring |
| *(Đức Kiên)* | Hoàng Đức Kiên | **QA** | Test plan · DoD · Data/model/UAT validation · Final QA report |

---

## Sprint Ownership

| Component | Owner | Sprint | Status |
|---|---|---|---|
| BRD + UML + Solution Architecture | Tech Lead | S1 | ✅ Done |
| ML Design Document | Model | S1 | ✅ Done |
| Repo setup + Docker skeleton | Pipeline | S1 | ✅ Done |
| Definition of Done + Test Plan | QA | S1 | ✅ Done |
| Bronze / Silver / Gold ETL | Data | S2 | ✅ Done |
| dbt models + data tests | Pipeline | S2 | ✅ Done |
| Airflow DAG (data pipeline) | Pipeline | S2 | ✅ Done |
| RFM scoring + segmentation | Model | S2 | ✅ Done |
| KPI marts | Data | S3 | ✅ Done |
| Churn model (XGBoost) + batch scoring | Model | S3 | ✅ Done |
| MLflow tracking + model registry | Pipeline | S3 | ✅ Done |
| Airflow DAG (ML extension) | Pipeline | S3 | ✅ Done |
| SHAP + feature explainability | Model | S4 | ✅ Done |
| K-Means clustering | Model | S4 | ✅ Done |
| Power BI dashboard | Data | S4 | ✅ Done |
| GitHub Actions CI/CD | Pipeline | S4 | ✅ Done |
| Streamlit demo (HF Spaces) | Pipeline | S4 | ✅ Done |
| Monitoring (data + model drift) | Pipeline | S4 | ✅ Done |
| Business Impact Report | Tech Lead | S4 | ✅ Done |
| Final QA report | QA | S4 | ✅ Done |
| LaTeX Technical Report | All | S4 | ✅ Done |
| Presentation slides + demo script | Tech Lead | S4 | ✅ Done |
| Demo video | Team Leader | S4 | ✅ Done |

---

## Branch Naming Convention

```
feature/<ticket>-<short-description>    # new features
pipeline/<ticket>-<short-description>   # pipeline / infra work
model/<ticket>-<short-description>      # ML model work
data/<ticket>-<short-description>       # data / dbt work
fix/<ticket>-<short-description>        # bug fixes
docs/<ticket>-<short-description>       # documentation only
```

Example: `pipeline/ACM1-76-setup-monitoring`

---

## Pull Request Process

1. Branch off `main` using the naming convention above
2. Make changes, commit with descriptive messages
3. Open PR → GitHub Actions CI must pass (lint + tests + dbt compile + docker build)
4. At least **1 review** from Tech Lead or another team member
5. Squash-merge into `main`

---

## Local Setup

```bash
# 1. Clone and install
git clone https://github.com/AIVIETNAM-AIO-PhanVanTien/retail-customer-intelligence-platform.git
cd retail-customer-intelligence-platform
make setup

# 2. Run full pipeline (requires data/raw/online_retail_listing.csv)
make pipeline

# 3. Train model
make train

# 4. Launch demo app
make serve
```

Or with Docker (full stack):
```bash
make docker-up   # Airflow :8080 · MLflow :5000 · Streamlit :8501
make docker-down
```

---

## Code Quality

```bash
make lint    # ruff check
make test    # pytest unit tests
```

CI runs automatically on every push and PR.
