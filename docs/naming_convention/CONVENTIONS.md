# Naming Conventions & Git Workflow

Single source of truth for **how we name things** and **how we collaborate** on this repo.
Read this before your first commit. When in doubt, match the closest existing example.

`Retail Customer Intelligence Platform · AIO Conquer 2026 · Module 01 · Jira: ACM1`

---

## 1. Git Branch Naming

`main` is **protected** — no direct pushes. Every change goes through a branch + Pull Request.

### Format

```
<type>/<JIRA-KEY>-<short-kebab-case-description>
```

Always embed the **Jira ticket key** (`ACM1-xx`) so the branch links back to the board.
Example: `data/ACM1-31-gold-star-schema`, `ml/ACM1-54-churn-xgboost`.

### Allowed types

| Type | Use for | Example |
| --- | --- | --- |
| `feat` | New feature / deliverable | `feat/ACM1-70-powerbi-dashboard` |
| `fix` | Bug fix | `fix/ACM1-30-rfm-null-customer` |
| `docs` | Docs only (BRD, README, plans) | `docs/ACM1-9-brd` |
| `data` | dbt models, marts, data modeling | `data/ACM1-31-gold-star-schema` |
| `ml` | Model, features, training, MLflow | `ml/ACM1-54-churn-xgboost` |
| `pipeline` | Airflow DAGs, Docker, infra | `pipeline/ACM1-35-ingest-dag` |
| `test` | Tests (pytest, dbt tests) | `test/ACM1-40-dag-integrity` |
| `ci` | CI/CD, GitHub Actions | `ci/ACM1-74-dbt-test-workflow` |
| `chore` | Tooling, config, cleanup | `chore/ruff-config` |
| `refactor` | Restructure, no behavior change | `refactor/feature-mart` |

### Rules

- **Type + key in lowercase**, description in kebab-case. No spaces, no camelCase.
- Keep the description short: 2–5 words describing the *what*, not the *how*.
- The `ACM1-xx` key is **required** — it links the branch (and its PR) to the Jira ticket.

### Owner → Jira role tag → typical branch prefix

| Jira Role Tag | Member | Typical branches |
| --- | --- | --- |
| TEAM LEADER / DATA | Võ Ngọc Gia Bảo | `data/*`, `feat/*-powerbi`, `docs/*-planning` |
| TECH LEAD | Phan Văn Tiến | `docs/*` (BRD/UML/architecture), `feat/*-mlflow` |
| MODEL | Phúc Nhân Nguyễn | `ml/*` |
| PIPELINE | Ngọc Phương | `pipeline/*`, `ci/*`, `data/*-dbt` |
| QA | Hoàng Đức Kiên | `test/*` |

---

## 2. Git Workflow (step by step)

```bash
# 0. Always start from an up-to-date main
git checkout main
git pull origin main

# 1. Create your branch (include the Jira key)
git checkout -b data/ACM1-31-gold-star-schema

# 2. Work + commit in small, logical chunks
git add path/to/changed/files
git commit -m "data: build gold star schema (ACM1-31)"

# 3. Push your branch (NEVER push to main)
git push -u origin data/ACM1-31-gold-star-schema

# 4. Open a Pull Request on GitHub → CI runs → reviewer approves → merge

# 5. After merge, clean up
git checkout main
git pull origin main
git branch -d data/ACM1-31-gold-star-schema
```

> ❌ `git push origin main` is blocked by branch protection.
> ❌ Never `git push --force` to a shared branch.
> ✅ Keep your branch rebased on the latest `main` before requesting review.

---

## 3. Commit Messages — Conventional Commits

### Format

```
<type>: <imperative, lowercase summary> (ACM1-xx)

[optional body — why, not what]
```

Append the **Jira key** in parentheses so commits trace back to the ticket.

### Types

`feat` · `fix` · `docs` · `data` · `ml` · `pipeline` · `test` · `ci` · `chore` · `refactor`
(same vocabulary as branch types — keeps history searchable).

### Good examples

```
feat: add RFM quintile scoring to fct_rfm (ACM1-36)
data: build dim_date with year/month/week grain (ACM1-31)
ml: train xgboost churn model, log run to mlflow (ACM1-54)
fix: handle cancelled invoices (C-prefix) in silver clean (ACM1-30)
test: add dbt not_null + accepted_values on segment (ACM1-40)
ci: run dbt test on sample in github actions (ACM1-74)
docs: add business impact report (ACM1-80)
```

### Rules

- Imperative mood: "add", not "added" / "adds".
- Summary ≤ 72 chars, no trailing period.
- One logical change per commit. Don't mix dbt models + dashboard + CI in one commit.

---

## 4. Pull Request Conventions

- **Title:** `type: short summary (ACM1-xx)` — same as the commit, with the Jira key.
- **Description must include:**
  - Link to the Jira ticket (`ACM1-xx`) and *what* changed and *why*.
  - Which sprint deliverable it covers (see `docs/planning/Project_Plan.md`).
  - How it was tested (dbt test / pytest output, screenshot for dashboard).
- **Reviewer:** at least **1 approval** + green CI before merge.
  - **Tech Lead** (Phan Văn Tiến) owns PR reviews for code/pipeline/ML (ACM1-41, ACM1-61).
  - **QA** (Hoàng Đức Kiên) signs off on data/model/UAT validation.
- **Merge strategy:** **Squash and merge** (keeps `main` history linear and clean).
- **Size:** prefer small PRs. If a PR touches > ~400 lines, consider splitting.

---

## 5. File & Folder Naming

| Item | Convention | Example |
| --- | --- | --- |
| Folders | lowercase, kebab or single word | `airflow/`, `dbt/`, `feature-store/` |
| Python modules | `snake_case.py` | `rfm_features.py`, `train_churn.py` |
| Python tests | `test_<module>.py` | `test_rfm_features.py` |
| SQL / dbt models | `snake_case.sql` | `stg_transactions.sql` |
| Notebooks | `snake_case.ipynb` (numbered if ordered) | `01_eda.ipynb` |
| Docs (Markdown) | `Snake_Case.md` or `UPPER.md` | `Project_Plan.md`, `BRD.md`, `README.md` |
| Configs | tool default | `docker-compose.yml`, `.env.example` |

---

## 6. Python Naming (PEP 8)

| Element | Convention | Example |
| --- | --- | --- |
| Variables / functions | `snake_case` | `recency_days`, `compute_rfm()` |
| Classes | `PascalCase` | `ChurnModel`, `FeatureBuilder` |
| Constants | `UPPER_SNAKE_CASE` | `AUC_THRESHOLD`, `CHURN_DAYS = 90` |
| Private | leading underscore | `_load_raw()` |
| Modules / packages | `snake_case` | `ml.features`, `pipeline.ingest` |

Linting: **ruff** (enforced in CI). Run `ruff check .` before pushing.

---

## 7. SQL & dbt Naming

### Layer prefixes (dbt model files)

| Layer | Prefix | Meaning | Example |
| --- | --- | --- | --- |
| Staging | `stg_` | 1:1 with source, light cleaning | `stg_online_retail.sql` |
| Intermediate | `int_` | reusable building blocks | `int_orders_joined.sql` |
| Marts — dimension | `dim_` | conformed dimensions | `dim_customer`, `dim_date` |
| Marts — fact | `fct_` / `fact_` | measures / events | `fact_transactions`, `fct_rfm` |
| Marts — aggregate | `mart_` | analytics / feature marts | `mart_customer_features` |

### Column rules

- `snake_case`, all lowercase. No spaces, no reserved words.
- Surrogate keys: `<entity>_sk` (e.g. `customer_sk`). Business keys: `<entity>_id` (e.g. `customer_id`).
- Booleans: `is_` / `has_` prefix (e.g. `churn_flag` → prefer `is_churn`).
- Dates: `_date` suffix; timestamps: `_at` suffix (e.g. `first_seen_date`, `scored_at`).
- Money: `_amount` suffix, GBP, FLOAT (e.g. `line_amount`, `monetary`).

### dbt tests (in `schema.yml`)

Standard tests on every mart: `unique`, `not_null` on keys, `accepted_values` on `segment`,
`relationships` for FK integrity. SQL linting via **sqlfluff** (CI).

---

## 8. Airflow DAG & Task Naming

| Item | Convention | Example |
| --- | --- | --- |
| DAG id | `snake_case`, verb-first | `retail_pipeline`, `daily_score_customers` |
| Task id | `snake_case`, action_object | `ingest_transactions`, `dbt_run`, `dbt_test`, `train_model`, `score_customers` |
| Schedule | document in DAG docstring | `@daily` |

DAG ids must be **unique** and match the pipeline stage they own.

---

## 9. ML / MLflow Naming

| Item | Convention | Example |
| --- | --- | --- |
| Experiment | `churn_<approach>` | `churn_baseline`, `churn_xgboost` |
| Run name | `<model>_<yyyymmdd>_<short>` | `xgboost_20260615_v1` |
| Registered model | `PascalCase` | `ChurnClassifier` |
| Model stage | MLflow standard | `Staging`, `Production` |
| Metrics | lowercase | `auc`, `precision`, `recall`, `f1` |
| Artifacts | `snake_case` | `feature_importance.png`, `confusion_matrix.png` |

---

## 10. Versioning & Releases (tags)

Semantic-ish tags for demo milestones:

```
v0.1.0  — Sprint 2 demo (18 Jun): CSV → Airflow → dbt → Star Schema → RFM
v0.2.0  — Sprint 3 demo (25 Jun): Customer → Features → Model → Churn Probability
v1.0.0  — Final delivery (30 Jun): full pipeline + Power BI + CI/CD + report (ACM1-81)
```

Tag format: `vMAJOR.MINOR.PATCH`. Create on `main` after a milestone merge:

```bash
git tag -a v0.1.0 -m "Sprint 2 demo: star schema + RFM"
git push origin v0.1.0
```

---

## Quick Reference

```
Branch   : <type>/<ACM1-xx>-<kebab-desc>   data/ACM1-31-gold-star-schema
Commit   : <type>: <summary> (ACM1-xx)     data: build gold star schema (ACM1-31)
PR title : <type>: <summary> (ACM1-xx)     ml: train churn xgboost model (ACM1-54)
dbt      : stg_ / int_ / dim_ / fct_ / mart_
Python   : snake_case fn · PascalCase class · UPPER_SNAKE const
Keys     : <entity>_sk (surrogate) · <entity>_id (business)
Review   : Tech Lead (code/ML) · QA (data/model/UAT) · 1 approval + green CI
Never    : push to main · force-push shared · mix concerns in one commit
```
