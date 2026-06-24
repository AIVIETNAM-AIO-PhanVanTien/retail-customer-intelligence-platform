---
title: Retail Churn Serving
emoji: 🛒
colorFrom: indigo
colorTo: red
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Retail Churn Serving

Streamlit demo that **serves the trained XGBoost churn model** from the
[Retail Customer Intelligence Platform](../README.md). KPI/segment BI reporting
is delivered in **Power BI** — this Space exposes only the ML model for
interactive scoring and retention targeting.

## Modes

| Tab | What it does |
| --- | --- |
| 🔎 Score a customer | Pick a customer → churn probability, risk tier, RFM segment, top churn drivers |
| 📋 Retention list | Filter the base by risk tier / segment / value → export a targeting CSV |
| 🧪 What-if | Adjust key levers on a synthetic customer and re-score live |

## Files (self-contained)

```
app/
├── app.py                  # Streamlit entry point
├── Dockerfile              # HF Spaces (Docker SDK, port 7860)
├── requirements.txt        # runtime deps only
├── model/
│   ├── model.pkl           # sklearn Pipeline (imputer + XGBoost)
│   └── metadata.json       # threshold, feature list, score summary
└── data/
    └── customers.parquet   # scored customer base for the demo
```

The app needs **only this folder** at runtime — no dbt / Airflow / `ml` package.

## Run locally

```bash
cd app
pip install -r requirements.txt
streamlit run app.py
# → http://localhost:8501
```

Or with Docker (mirrors the Space):

```bash
docker build -t churn-serving app/
docker run -p 7860:7860 churn-serving
# → http://localhost:7860
```

## Deploy to HuggingFace Spaces

1. Create a new Space → **SDK: Docker**.
2. Copy the **contents of this `app/` folder** into the Space repo root
   (so `Dockerfile`, `app.py`, `model/`, `data/` sit at the top level).
3. Push — the Space builds the image and serves on port 7860.

> ⚠️ `model/model.pkl` is pickled with **scikit-learn 1.7.2**. Keep the pin in
> `requirements.txt` aligned with the version used at training time, or
> unpickling may fail.

## Refreshing the model

Re-export from the latest training run (writes `model/`, `data/`, metadata):

```bash
python -m scripts.export_serving_app   # from repo root
```
