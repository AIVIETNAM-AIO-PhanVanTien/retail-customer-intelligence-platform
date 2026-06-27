# ─── Retail Customer Intelligence Platform — Makefile ─────────────────────────
# Usage: make <target>
# Requires: Python 3.10+, Docker, dbt-core installed (see requirements.txt)

.PHONY: help setup lint test dbt-run dbt-test pipeline train cluster \
        export-app serve docker-up docker-down clean

# Default target
help:
	@echo ""
	@echo "Retail Customer Intelligence Platform"
	@echo "======================================"
	@echo ""
	@echo "Setup"
	@echo "  make setup          Install all Python dependencies"
	@echo ""
	@echo "Code quality"
	@echo "  make lint           Run ruff linter"
	@echo "  make test           Run unit tests (skip integration)"
	@echo "  make test-all       Run all tests including integration"
	@echo ""
	@echo "Data pipeline"
	@echo "  make pipeline       Run full ETL pipeline (bronze → silver → gold)"
	@echo "  make dbt-run        Run dbt transformations"
	@echo "  make dbt-test       Run dbt data tests"
	@echo ""
	@echo "ML"
	@echo "  make train          Train churn model"
	@echo "  make cluster        Run K-Means clustering pipeline"
	@echo "  make export-app     Export serving bundle to app/"
	@echo ""
	@echo "Serving"
	@echo "  make serve          Run Streamlit demo app locally (port 8501)"
	@echo "  make docker-up      Start full stack (Airflow + MLflow + Streamlit)"
	@echo "  make docker-down    Stop full stack"
	@echo ""
	@echo "Utilities"
	@echo "  make clean          Remove generated artifacts (dbt target, pycache)"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────────────────
setup:
	pip install -r requirements.txt
	@echo "✓ Dependencies installed"

# ── Code quality ──────────────────────────────────────────────────────────────
lint:
	ruff check . --output-format=github

test:
	pytest tests/ -m "not integration" -q --tb=short

test-all:
	pytest tests/ -q --tb=short

# ── Data pipeline ─────────────────────────────────────────────────────────────
pipeline:
	python -m src.etl.bronze_ingest
	python -m src.etl.silver_transform
	python -m src.etl.gold_build
	$(MAKE) dbt-run
	$(MAKE) dbt-test
	@echo "✓ Full pipeline complete"

dbt-run:
	cd dbt && dbt run --profiles-dir . --project-dir .

dbt-test:
	cd dbt && dbt test --profiles-dir . --project-dir .

# ── ML ────────────────────────────────────────────────────────────────────────
train:
	python -m ml.churn.pipeline

cluster:
	python -m ml.clustering.pipeline

export-app:
	python -m scripts.export_serving_app
	@echo "✓ Serving bundle exported to app/"

# ── Serving ───────────────────────────────────────────────────────────────────
serve:
	streamlit run app/app.py --server.port 8501

docker-up:
	docker compose up --build -d
	@echo "✓ Stack running"
	@echo "  Airflow  → http://localhost:8080"
	@echo "  MLflow   → http://localhost:5000"
	@echo "  Streamlit → http://localhost:8501"

docker-down:
	docker compose down

# ── Utilities ─────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf dbt/target/
	@echo "✓ Cleaned"
