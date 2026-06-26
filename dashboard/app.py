import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="Retail Pipeline Ops", layout="wide")
st.title("🔍 Pipeline Ops Dashboard")

MONITORING_PATH = Path("data/gold/mart_monitoring/mart_monitoring.parquet")

if not MONITORING_PATH.exists():
    st.warning("No monitoring data found. Run the pipeline first.")
    st.stop()

df = pd.read_parquet(MONITORING_PATH)
latest_date = df["run_date"].max()
latest = df[df["run_date"] == latest_date]

# Helper to get a metric value by name
def get_metric(name, default=0):
    row = latest[latest["metric_name"] == name]
    return row["metric_value"].values[0] if len(row) > 0 else default

st.subheader(f"Latest Run — {latest_date}")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Customers Scored", int(get_metric("total_customers_scored")))
col2.metric("High Risk %", f"{get_metric('pct_high_risk')*100:.1f}%")
col3.metric("Score Mean", f"{get_metric('score_mean'):.4f}")
col4.metric("Features Drifted", int(get_metric("n_features_drifted")))

st.divider()

# Model drift over time
st.subheader("Model Drift Over Time")
model_drift = df[df["category"] == "model_drift"]
if not model_drift.empty:
    pivot = model_drift.pivot_table(
        index="run_date", columns="metric_name", values="metric_value"
    ).reset_index()
    if "pct_high_risk" in pivot.columns:
        st.line_chart(pivot.set_index("run_date")[["pct_high_risk"]])
    if "score_mean" in pivot.columns:
        st.line_chart(pivot.set_index("run_date")[["score_mean"]])

# Data drift over time
st.subheader("Data Drift Over Time")
data_drift = df[df["category"] == "data_drift"]
if data_drift.empty:
    st.info("No data drift metrics yet — feature_stats not in model metadata.")
else:
    st.dataframe(data_drift.sort_values("run_date", ascending=False))

st.divider()
st.subheader("Full Monitoring History")
st.dataframe(df.sort_values(["run_date", "category"], ascending=False))