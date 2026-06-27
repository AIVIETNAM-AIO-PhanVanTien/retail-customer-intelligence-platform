"""Churn Serving — Streamlit ML demo (HuggingFace Spaces).

Self-contained churn-prediction service. Loads the trained XGBoost
sklearn Pipeline and serves three modes:

  1. Score a customer  — pick a customer, see churn probability + drivers
  2. Retention list    — filter the base, export a targeting CSV
  3. What-if           — adjust key features, score a synthetic customer

This app only needs the files shipped in this folder:
  model/model.pkl · model/metadata.json · data/customers.parquet
The rest of the repo (dbt / airflow / ml package) is NOT required at runtime.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

HERE = Path(__file__).resolve().parent
MODEL_PATH = HERE / "model" / "model.pkl"
META_PATH = HERE / "model" / "metadata.json"
DATA_PATH = HERE / "data" / "customers.parquet"
CLUSTER_PROFILES_PATH = HERE / "data" / "cluster_profiles.parquet"
MONITORING_PATH = HERE / "data" / "monitoring.parquet"

st.set_page_config(
    page_title="Churn Serving · Retail Intelligence",
    page_icon="🛒",
    layout="wide",
)


# ── Loaders (cached) ─────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="Loading model…")
def load_model():
    with open(MODEL_PATH, "rb") as fh:
        return pickle.load(fh)


@st.cache_data(show_spinner=False)
def load_metadata() -> dict:
    with open(META_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@st.cache_data(show_spinner="Loading customers…")
def load_customers() -> pd.DataFrame:
    return pd.read_parquet(DATA_PATH)


@st.cache_data(show_spinner=False)
def load_cluster_profiles() -> pd.DataFrame | None:
    if not CLUSTER_PROFILES_PATH.exists():
        return None
    return pd.read_parquet(CLUSTER_PROFILES_PATH)


@st.cache_data(show_spinner=False)
def load_monitoring() -> pd.DataFrame | None:
    if not MONITORING_PATH.exists():
        return None
    return pd.read_parquet(MONITORING_PATH)


model = load_model()
meta = load_metadata()
customers = load_customers()
FEATURES: list[str] = meta["feature_columns"]


def risk_tier(p: float) -> str:
    tiers = meta["risk_tiers"]
    if p >= tiers["High"]:
        return "High"
    if p >= tiers["Medium"]:
        return "Medium"
    return "Low"


TIER_COLOR = {"High": "#d62728", "Medium": "#ff7f0e", "Low": "#2ca02c"}


def feature_importance() -> pd.DataFrame:
    """Global gain importance from the XGBoost step, mapped to feature names."""
    xgb = model.named_steps["model"]
    imp = np.asarray(xgb.feature_importances_, dtype=float)
    return (
        pd.DataFrame({"feature": FEATURES, "importance": imp})
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )


def score_frame(df: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(df[FEATURES])[:, 1]


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🛒 Churn Serving")
    st.caption("Retail Customer Intelligence Platform")
    st.divider()

    threshold = st.slider(
        "Decision threshold",
        min_value=0.05,
        max_value=0.95,
        value=float(meta.get("optimal_threshold", 0.5)),
        step=0.01,
        help="Probability ≥ threshold ⇒ flagged as churn.",
    )

    ss = meta.get("score_summary", {})
    st.divider()
    st.markdown("**Model**")
    st.write(f"Type: `{meta.get('model_type', 'XGBoost')}`")
    st.write(f"Features: **{meta.get('n_features', len(FEATURES))}**")
    st.write(f"Customers: **{meta.get('n_customers', len(customers)):,}**")
    if ss:
        st.write(f"Mean churn prob: **{ss.get('mean', 0):.2f}**")
    st.caption(f"Run `{meta.get('source_run_id', 'n/a')[:8]}`")


st.title("Customer Churn — Model Serving")
st.caption(
    "Live XGBoost scoring for retention targeting. "
    "BI/KPI reporting lives in Power BI; this Space serves the ML model."
)

tab_overview, tab_one, tab_list, tab_whatif, tab_clusters, tab_monitoring = st.tabs(
    ["📊 Overview", "🔎 Score a customer", "📋 Retention list", "🧪 What-if", "🔵 Clustering", "📈 Monitoring"]
)


# ── Tab 0: overview dashboard ────────────────────────────────────────────────
with tab_overview:
    # Pre-compute scored base at sidebar threshold
    ov = customers.copy()
    ov["churn_flag"] = (ov["churn_probability"] >= threshold).astype(int)
    ov["risk_tier"] = ov["churn_probability"].map(risk_tier)

    # ── KPI row ──────────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total customers", f"{len(ov):,}")
    k2.metric("Churn rate", f"{ov['churn_flag'].mean():.1%}")
    k3.metric("High risk", f"{(ov['risk_tier'] == 'High').sum():,}")
    k4.metric("Medium risk", f"{(ov['risk_tier'] == 'Medium').sum():,}")
    k5.metric("Revenue at risk (£)", f"{ov.loc[ov['churn_flag'] == 1, 'monetary'].sum():,.0f}")

    st.divider()

    col_left, col_right = st.columns(2)

    # Score distribution histogram
    with col_left:
        st.markdown("**Churn probability distribution**")
        hist = go.Figure(
            go.Histogram(
                x=ov["churn_probability"],
                nbinsx=40,
                marker_color="#1f77b4",
                opacity=0.8,
            )
        )
        hist.add_vline(
            x=threshold,
            line_dash="dash",
            line_color="red",
            annotation_text=f"threshold={threshold:.2f}",
        )
        hist.update_layout(
            height=300,
            margin=dict(t=10, b=10, l=10, r=10),
            xaxis_title="Churn probability",
            yaxis_title="Customers",
        )
        st.plotly_chart(hist, use_container_width=True)

    # Risk tier breakdown
    with col_right:
        st.markdown("**Risk tier breakdown**")
        tier_counts = ov["risk_tier"].value_counts().reindex(["High", "Medium", "Low"], fill_value=0)
        pie = go.Figure(
            go.Pie(
                labels=tier_counts.index.tolist(),
                values=tier_counts.values.tolist(),
                marker_colors=["#d62728", "#ff7f0e", "#2ca02c"],
                hole=0.4,
            )
        )
        pie.update_layout(height=300, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(pie, use_container_width=True)

    # RFM segment breakdown
    if "segment" in ov.columns:
        st.markdown("**RFM segment breakdown**")
        seg_summary = (
            ov.groupby("segment", observed=True)
            .agg(
                customers=("customer_id", "count"),
                churn_rate=("churn_flag", "mean"),
                avg_monetary=("monetary", "mean"),
            )
            .sort_values("churn_rate", ascending=False)
            .reset_index()
        )
        seg_summary["churn_rate"] = seg_summary["churn_rate"].map("{:.1%}".format)
        seg_summary["avg_monetary"] = seg_summary["avg_monetary"].map("£{:,.0f}".format)
        st.dataframe(seg_summary, hide_index=True, use_container_width=True)

    # Model info
    st.divider()
    st.markdown("**Model info**")
    m = meta.get("metrics", {})
    mi1, mi2, mi3, mi4 = st.columns(4)
    mi1.metric("Model", meta.get("model_type", "XGBoost"))
    mi2.metric("Test AUC", f"{m.get('auc_roc', 0):.4f}" if m.get("auc_roc") else "—")
    mi3.metric("Features", meta.get("n_features", len(FEATURES)))
    mi4.metric("Exported", meta.get("exported_at", "—")[:10])


# ── Tab 1: single customer ───────────────────────────────────────────────────
with tab_one:
    col_pick, _ = st.columns([2, 3])
    with col_pick:
        cid = st.selectbox(
            "Customer ID",
            options=customers["customer_id"].tolist(),
            index=0,
        )
    row = customers.loc[customers["customer_id"] == cid].iloc[0]
    prob = float(score_frame(row.to_frame().T)[0])
    tier = risk_tier(prob)
    flagged = prob >= threshold

    g1, g2, g3, g4 = st.columns(4)
    g1.metric("Churn probability", f"{prob:.1%}")
    g2.metric("Risk tier", tier)
    g3.metric("Decision", "⚠️ CHURN" if flagged else "✅ Retain")
    g4.metric("RFM segment", str(row.get("segment", "—")))

    gauge = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=prob * 100,
            number={"suffix": "%"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": TIER_COLOR[tier]},
                "threshold": {
                    "line": {"color": "black", "width": 3},
                    "value": threshold * 100,
                },
                "steps": [
                    {"range": [0, 40], "color": "#e7f4e7"},
                    {"range": [40, 70], "color": "#fdeed9"},
                    {"range": [70, 100], "color": "#f8e0e0"},
                ],
            },
        )
    )
    gauge.update_layout(height=260, margin=dict(t=20, b=10, l=20, r=20))

    c_left, c_right = st.columns([1, 1])
    with c_left:
        st.plotly_chart(gauge, width="stretch")
    with c_right:
        st.markdown("**Customer snapshot**")
        snap = {
            "Recency (days)": row.get("recency_days"),
            "Frequency": row.get("frequency"),
            "Monetary": row.get("monetary"),
            "Avg order value": row.get("avg_order_value"),
            "Tenure (days)": row.get("tenure_days"),
            "One-time buyer": bool(row.get("is_one_time_buyer", 0)),
        }
        st.table(
            pd.DataFrame(
                {"value": [snap[k] for k in snap]}, index=list(snap)
            ).round(2)
        )

    # Top drivers (global gain) + this customer's percentile on each
    st.markdown("**Top churn drivers** (model gain importance)")
    top = feature_importance().head(8).copy()
    pct = {
        f: float((customers[f] <= row[f]).mean()) for f in top["feature"]
    }
    top["customer_percentile"] = top["feature"].map(pct)
    bar = go.Figure(
        go.Bar(
            x=top["importance"][::-1],
            y=top["feature"][::-1],
            orientation="h",
            marker_color="#1f77b4",
        )
    )
    bar.update_layout(height=300, margin=dict(t=10, b=10, l=10, r=10))
    st.plotly_chart(bar, width="stretch")
    st.caption(
        "Percentile = where this customer sits vs the base on each driver "
        "(1.0 = highest)."
    )
    st.dataframe(
        top.assign(
            importance=top["importance"].round(4),
            customer_percentile=top["customer_percentile"].round(2),
        ),
        hide_index=True,
        width="stretch",
    )


# ── Tab 2: retention list ────────────────────────────────────────────────────
with tab_list:
    scored = customers.copy()
    scored["churn_probability"] = (
        score_frame(scored)
        if "churn_probability" not in scored
        else scored["churn_probability"]
    )
    scored["churn_flag"] = (scored["churn_probability"] >= threshold).astype(int)
    scored["risk_tier"] = scored["churn_probability"].map(risk_tier)

    f1, f2, f3 = st.columns(3)
    tiers_sel = f1.multiselect(
        "Risk tiers", ["High", "Medium", "Low"], default=["High"]
    )
    segs = sorted(scored["segment"].dropna().unique().tolist())
    seg_sel = f2.multiselect("RFM segments", segs, default=[])
    min_mon = f3.number_input("Min monetary (£)", value=0.0, step=100.0)

    view = scored[scored["risk_tier"].isin(tiers_sel)]
    if seg_sel:
        view = view[view["segment"].isin(seg_sel)]
    view = view[view["monetary"] >= min_mon]
    view = view.sort_values("churn_probability", ascending=False)

    m1, m2, m3 = st.columns(3)
    m1.metric("Customers targeted", f"{len(view):,}")
    m2.metric("Revenue at stake (£)", f"{view['monetary'].sum():,.0f}")
    m3.metric(
        "Share of base",
        f"{(len(view) / max(len(scored), 1)):.1%}",
    )

    cols = [
        "customer_id",
        "segment",
        "churn_probability",
        "risk_tier",
        "recency_days",
        "frequency",
        "monetary",
    ]
    st.dataframe(
        view[cols].assign(
            churn_probability=view["churn_probability"].round(3),
            monetary=view["monetary"].round(0),
        ),
        hide_index=True,
        width="stretch",
        height=420,
    )
    st.download_button(
        "⬇️ Download retention list (CSV)",
        data=view[cols].to_csv(index=False).encode("utf-8"),
        file_name="retention_list.csv",
        mime="text/csv",
    )


# ── Tab 3: what-if ───────────────────────────────────────────────────────────
with tab_whatif:
    st.caption(
        "Start from the median customer and adjust the key levers. "
        "Untouched features use the population median."
    )
    base = customers[FEATURES].median(numeric_only=True)
    levers = [
        "recency_days",
        "frequency",
        "monetary",
        "frequency_last_90d",
        "avg_order_value",
        "tenure_days",
    ]
    levers = [f for f in levers if f in FEATURES]

    cols = st.columns(3)
    synth = base.copy()
    for i, f in enumerate(levers):
        lo = float(customers[f].quantile(0.01))
        hi = float(customers[f].quantile(0.99))
        synth[f] = cols[i % 3].slider(
            f, min_value=lo, max_value=hi, value=float(base[f])
        )

    synth_df = synth.to_frame().T[FEATURES]
    p = float(score_frame(synth_df)[0])
    t = risk_tier(p)
    a, b, c = st.columns(3)
    a.metric("Churn probability", f"{p:.1%}")
    b.metric("Risk tier", t)
    c.metric("Decision", "⚠️ CHURN" if p >= threshold else "✅ Retain")


# ── Tab 4: clustering ────────────────────────────────────────────────────────
with tab_clusters:
    profiles = load_cluster_profiles()
    if profiles is None:
        st.warning("cluster_profiles.parquet not found. Re-run `scripts/export_serving_app.py`.")
    else:
        has_cluster = "cluster_name" in customers.columns

        # ── KPI row ──────────────────────────────────────────────────────────
        ck1, ck2, ck3, ck4 = st.columns(4)
        ck1.metric("Clusters", int(len(profiles)))
        ck2.metric("Total customers", f"{len(customers):,}")
        if has_cluster:
            largest = profiles.loc[profiles["cluster_size"].idxmax(), "cluster_name"]
            ck3.metric("Largest cluster", largest)
            smallest = profiles.loc[profiles["cluster_size"].idxmin(), "cluster_name"]
            ck4.metric("Smallest cluster", smallest)

        st.divider()

        cl_left, cl_right = st.columns(2)

        # Cluster distribution pie
        with cl_left:
            st.markdown("**Cluster distribution**")
            pie_c = go.Figure(
                go.Pie(
                    labels=profiles["cluster_name"].tolist(),
                    values=profiles["cluster_size"].tolist(),
                    hole=0.4,
                    textinfo="label+percent",
                )
            )
            pie_c.update_layout(height=320, margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
            st.plotly_chart(pie_c, use_container_width=True)

        # Key feature comparison bar
        with cl_right:
            st.markdown("**Avg monetary by cluster**")
            bar_mon = go.Figure(
                go.Bar(
                    x=profiles["cluster_name"],
                    y=profiles["monetary"].round(0),
                    marker_color=["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
                                  "#9467bd", "#8c564b"][:len(profiles)],
                    text=profiles["monetary"].round(0).astype(int),
                    textposition="outside",
                )
            )
            bar_mon.update_layout(
                height=320,
                margin=dict(t=10, b=10, l=10, r=10),
                yaxis_title="Avg monetary (£)",
                xaxis_tickangle=-20,
            )
            st.plotly_chart(bar_mon, use_container_width=True)

        # Recency + Frequency grouped bar
        st.markdown("**Avg recency (days) & frequency by cluster**")
        fig_rf = go.Figure()
        fig_rf.add_trace(go.Bar(
            name="Recency (days)",
            x=profiles["cluster_name"],
            y=profiles["recency_days"].round(1),
            yaxis="y",
        ))
        fig_rf.add_trace(go.Bar(
            name="Frequency",
            x=profiles["cluster_name"],
            y=profiles["frequency"].round(1),
            yaxis="y2",
        ))
        fig_rf.update_layout(
            height=320,
            barmode="group",
            margin=dict(t=10, b=10, l=10, r=10),
            yaxis=dict(title="Recency (days)"),
            yaxis2=dict(title="Frequency", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.08),
        )
        st.plotly_chart(fig_rf, use_container_width=True)

        # Churn rate by cluster
        if has_cluster:
            st.markdown("**Churn rate by cluster** (at current threshold)")
            cust_c = customers.copy()
            cust_c["churn_flag"] = (cust_c["churn_probability"] >= threshold).astype(int)
            churn_by_cluster = (
                cust_c.groupby("cluster_name", observed=True)["churn_flag"]
                .mean()
                .reset_index()
                .rename(columns={"churn_flag": "churn_rate"})
                .sort_values("churn_rate", ascending=False)
            )
            bar_churn = go.Figure(
                go.Bar(
                    x=churn_by_cluster["cluster_name"],
                    y=(churn_by_cluster["churn_rate"] * 100).round(1),
                    text=(churn_by_cluster["churn_rate"] * 100).round(1).astype(str) + "%",
                    textposition="outside",
                    marker_color="#d62728",
                )
            )
            bar_churn.update_layout(
                height=280,
                margin=dict(t=10, b=10, l=10, r=10),
                yaxis_title="Churn rate (%)",
                xaxis_tickangle=-20,
            )
            st.plotly_chart(bar_churn, use_container_width=True)

        st.divider()

        # Cluster profiles table
        st.markdown("**Cluster profiles**")
        disp_cols = [c for c in [
            "cluster_name", "cluster_size", "cluster_pct",
            "recency_days", "frequency", "monetary",
            "avg_order_value", "tenure_days", "cancellation_rate",
        ] if c in profiles.columns]
        st.dataframe(
            profiles[disp_cols].round(2).rename(columns={
                "cluster_name": "Cluster",
                "cluster_size": "Customers",
                "cluster_pct": "% Base",
                "recency_days": "Recency (d)",
                "frequency": "Frequency",
                "monetary": "Monetary (£)",
                "avg_order_value": "Avg order (£)",
                "tenure_days": "Tenure (d)",
                "cancellation_rate": "Cancel rate",
            }),
            hide_index=True,
            use_container_width=True,
        )

        # Customer list per cluster
        if has_cluster:
            st.divider()
            st.markdown("**Customers by cluster**")
            selected_cluster = st.selectbox(
                "Select cluster",
                options=sorted(customers["cluster_name"].dropna().unique().tolist()),
            )
            cluster_view = customers[customers["cluster_name"] == selected_cluster].copy()
            cluster_view["churn_flag"] = (cluster_view["churn_probability"] >= threshold).astype(int)
            cluster_view = cluster_view.sort_values("churn_probability", ascending=False)
            cv_cols = [c for c in [
                "customer_id", "segment", "cluster_name",
                "churn_probability", "recency_days", "frequency", "monetary",
            ] if c in cluster_view.columns]
            st.caption(f"{len(cluster_view):,} customers in **{selected_cluster}**")
            st.dataframe(
                cluster_view[cv_cols].assign(
                    churn_probability=cluster_view["churn_probability"].round(3),
                    monetary=cluster_view["monetary"].round(0),
                ),
                hide_index=True,
                use_container_width=True,
                height=380,
            )


# ── Tab 5: monitoring ────────────────────────────────────────────────────────
with tab_monitoring:
    mon_df = load_monitoring()
    if mon_df is None:
        st.warning("monitoring.parquet not found. Re-run `scripts/export_serving_app.py`.")
    else:
        model_drift = mon_df[mon_df["category"] == "model_drift"]
        data_drift = mon_df[mon_df["category"] == "data_drift"]

        def _get(df: pd.DataFrame, name: str, default: float = 0.0) -> float:
            row = df[df["metric_name"] == name]["metric_value"]
            return float(row.iloc[0]) if len(row) > 0 else default

        # ── KPI row ──────────────────────────────────────────────────────────
        st.subheader(f"Latest run — {mon_df['run_date'].max()}")
        mk1, mk2, mk3, mk4 = st.columns(4)
        mk1.metric("Customers scored", f"{int(_get(model_drift, 'total_customers_scored')):,}")
        mk2.metric("Score mean", f"{_get(model_drift, 'score_mean'):.4f}")
        mk3.metric("High risk %", f"{_get(model_drift, 'pct_high_risk') * 100:.1f}%")
        mk4.metric("Features drifted", int(_get(data_drift, "n_features_drifted")))

        st.divider()

        mon_left, mon_right = st.columns(2)

        # Score distribution
        with mon_left:
            st.markdown("**Score distribution (current run)**")
            percentiles = ["p25", "p50", "p75", "p90"]
            pct_vals = [_get(model_drift, f"score_{p}") for p in percentiles]
            bar_score = go.Figure(
                go.Bar(
                    x=[f"P{p[1:]}" for p in percentiles],
                    y=[round(v * 100, 1) for v in pct_vals],
                    text=[f"{v * 100:.1f}%" for v in pct_vals],
                    textposition="outside",
                    marker_color="#1f77b4",
                )
            )
            bar_score.update_layout(
                height=300,
                margin=dict(t=10, b=10, l=10, r=10),
                yaxis_title="Churn probability (%)",
                yaxis_range=[0, 100],
            )
            st.plotly_chart(bar_score, use_container_width=True)

        # Risk tier breakdown
        with mon_right:
            st.markdown("**Risk tier breakdown (current run)**")
            tier_names = ["High risk", "Medium risk", "Low risk"]
            tier_vals = [
                int(_get(model_drift, "n_high_risk")),
                int(_get(model_drift, "n_medium_risk")),
                int(_get(model_drift, "n_low_risk")),
            ]
            pie_tier = go.Figure(
                go.Pie(
                    labels=tier_names,
                    values=tier_vals,
                    marker_colors=["#d62728", "#ff7f0e", "#2ca02c"],
                    hole=0.4,
                )
            )
            pie_tier.update_layout(height=300, margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(pie_tier, use_container_width=True)

        # Score distribution z-score
        score_z = _get(model_drift, "score_distribution_z")
        z_color = "🟢" if score_z < 1.0 else "🟡" if score_z < 2.0 else "🔴"
        st.info(f"{z_color} Score distribution z-score vs training baseline: **{score_z:.4f}** "
                f"{'(stable)' if score_z < 2.0 else '⚠️ drift detected'}")

        st.divider()

        # Data drift summary
        st.markdown("**Data drift summary**")
        n_checked = int(_get(data_drift, "n_features_checked"))
        n_drifted = int(_get(data_drift, "n_features_drifted"))
        drift_rate = _get(data_drift, "drift_rate")

        dd1, dd2, dd3 = st.columns(3)
        dd1.metric("Features checked", n_checked)
        dd2.metric("Features drifted (|z|>3)", n_drifted)
        dd3.metric("Drift rate", f"{drift_rate:.1%}")

        if n_checked == 0:
            st.caption(
                "No feature baseline in model metadata — data drift detection requires "
                "`feature_stats` to be saved during training."
            )
        elif n_drifted == 0:
            st.success("No data drift detected across all checked features.")
        else:
            st.warning(f"{n_drifted} feature(s) drifted beyond z=3 threshold.")

        st.divider()

        # Full monitoring log
        st.markdown("**Full monitoring log**")
        st.dataframe(
            mon_df.sort_values(["run_date", "category"], ascending=[False, True]),
            hide_index=True,
            use_container_width=True,
        )
