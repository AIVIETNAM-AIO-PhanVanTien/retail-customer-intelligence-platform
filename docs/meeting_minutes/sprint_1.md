# Meeting Minutes — Sprint 1 Kickoff

**Date:** 05 June 2026 · 22:00 ICT
**Project:** Retail Customer Intelligence Platform (ACM1)
**Attendees:** Phan Văn Tiến (Tech Lead), Võ Ngọc Gia Bảo (Team Leader/Data), Phúc Nhân Nguyễn (Model), Ngọc Phương (Pipeline), Hoàng Đức Kiên (QA)

---

## Agenda

1. Topic selection and project scope
2. Role assignment
3. Sprint 1 deliverables
4. Branch/repo conventions

---

## Decisions

### 1. Topic & Dataset
- Selected **Project #22 + #20**: Retail Customer Intelligence Platform
- Dataset: `online_retail_listing.csv` (~1.01M rows, UK e-commerce 2009–2011)
- Dates will be rebased to present so recency/churn windows are meaningful

### 2. Architecture
- **Medallion lakehouse**: Bronze (raw) → Silver (clean) → Gold (star schema + marts)
- **Engine**: DuckDB (in-process, no infra overhead)
- **Transform**: dbt-duckdb
- **Orchestration**: Airflow (Docker)
- **ML tracking**: MLflow
- **Dashboard**: Power BI (KPI/BI) + Streamlit (ML serving demo)
- **No** Kafka / Spark / Kubernetes — maturity via SDLC completeness, not framework count

### 3. Role Assignments
| Role | Member | Primary deliverables |
|---|---|---|
| Tech Lead | Phan Văn Tiến | BRD, UML, architecture, PR reviews |
| Team Leader / Data | Võ Ngọc Gia Bảo | EDA, star schema, dbt models, Power BI |
| Model | Phúc Nhân Nguyễn | RFM, churn model, clustering, SHAP |
| Pipeline | Ngọc Phương | Repo, Docker, Airflow, CI/CD, monitoring |
| QA | Hoàng Đức Kiên | DoD, test plan, validation |

### 4. Conventions
- Branch naming: `<role>/<ticket>-<desc>` (e.g. `pipeline/ACM1-01-repo-setup`)
- All work tracked in Jira under project key `ACM1`
- PRs require 1 review before merge; CI must pass

---

## Action Items

| Owner | Task | Due |
|---|---|---|
| Tech Lead | Draft BRD (pain points, objectives, stakeholders, scope) | 07 Jun |
| Tech Lead | UML diagrams (Use Case / Activity / Sequence) | 09 Jun |
| Tech Lead | Solution architecture + data flow diagram | 09 Jun |
| Data | Data profiling & EDA on raw CSV | 09 Jun |
| Data | Star Schema ERD + Data Dictionary | 11 Jun |
| Model | ML Design Document (churn label logic, features, metrics) | 09 Jun |
| Pipeline | GitHub repo setup (branches, .gitignore, folder structure) | 07 Jun |
| Pipeline | Docker Compose skeleton (Airflow, dbt, DuckDB, MLflow) | 11 Jun |
| QA | Definition of Done (all 4 sprints) | 09 Jun |
| QA | Test Plan & checklist | 09 Jun |
| ALL | Study assigned role docs (Git/Jira) | 07 Jun |

---

## Next Meeting

**Date:** 11 June 2026 · 22:00 ICT — Sprint 1 Demo
