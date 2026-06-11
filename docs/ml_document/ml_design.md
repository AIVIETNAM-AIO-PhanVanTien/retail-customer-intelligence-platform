# ML Design Document

**Project:** Retail Customer Intelligence Platform
**Author:** Phúc Nhân Nguyễn (MODEL)
**Sprint:** S1 — Discovery & Onboarding
**Date:** 2026-06-10
**Status:** Draft v1.3

---

## Table of Contents

1. [RFM Segmentation Design](#1-rfm-segmentation-design)
2. [Churn Label Logic](#2-churn-label-logic)
3. [Feature Engineering Plan](#3-feature-engineering-plan)
4. [Candidate Models](#4-candidate-models)
5. [Evaluation Metrics & Thresholds](#5-evaluation-metrics--thresholds)
6. [Target Metrics Summary](#6-target-metrics-summary)

---

## 1. RFM Segmentation Design

### 1.1 What is RFM?

RFM analysis scores customers on three dimensions:

| Dimension | Definition | Calculation |
|-----------|-----------|-------------|
| **Recency (R)** | How recently a customer made a purchase | `SNAPSHOT_DATE − last_purchase_date` (in days) |
| **Frequency (F)** | How often a customer purchases | Count of **distinct invoices** (excluding cancellations) |
| **Monetary (M)** | How much a customer spends | Sum of `Quantity × Price` across all valid transactions |

### 1.2 Scoring Method: Quintile-Based (1–5)

Each dimension is divided into **5 quintiles** using `pd.qcut()`:

| Score | Meaning | Percentile Range |
|-------|---------|-----------------| 
| 5 | Best | 0–20th percentile (Recency) / 80–100th (F, M) |
| 4 | Good | 20–40th / 60–80th |
| 3 | Average | 40–60th |
| 2 | Below Average | 60–80th / 20–40th |
| 1 | Worst | 80–100th (Recency) / 0–20th (F, M) |

> **Note:** For Recency, **lower is better** (purchased recently), so scoring is inverted: lowest days → score 5.

### 1.3 RFM Score Composition

```
RFM_Score = R_Score × 100 + F_Score × 10 + M_Score
```

Example: A customer with R=5, F=4, M=3 → `RFM_Score = 543`

### 1.4 Segment Mapping Rules

Customers are mapped to **8 segments** based on R, F, M score combinations:

| Segment | R Score | F Score | M Score | Business Meaning |
|---------|---------|---------|---------|-----------------| 
| **Champions** | 4–5 | 4–5 | 4–5 | Best customers: recent, frequent, high-value |
| **Loyal Customers** | 3–5 | 3–5 | 3–5 | Consistent buyers (not necessarily top R) |
| **Potential Loyalists** | 4–5 | 2–3 | 2–3 | Recent buyers with moderate engagement |
| **New Customers** | 4–5 | 1 | 1–2 | Just arrived, first or second purchase |
| **Promising** | 3–4 | 1–2 | 1–2 | Somewhat recent, low engagement |
| **Need Attention** | 2–3 | 2–3 | 2–3 | Slipping away — average across the board |
| **At Risk** | 1–2 | 3–5 | 3–5 | Were good customers, but haven't returned |
| **Lost / Hibernating** | 1–2 | 1–2 | 1–2 | Low on all dimensions — disengaged |

**Implementation (pseudo-code):**

```python
def assign_rfm_segment(r, f, m):
    if r >= 4 and f >= 4 and m >= 4:
        return "Champions"
    elif r >= 3 and f >= 3 and m >= 3:
        return "Loyal Customers"
    elif r >= 4 and f <= 3 and m <= 3:
        return "Potential Loyalists"
    elif r >= 4 and f == 1:
        return "New Customers"
    elif r >= 3 and f <= 2:
        return "Promising"
    elif r <= 3 and f >= 2 and m >= 2:
        return "Need Attention"
    elif r <= 2 and (f >= 3 or m >= 3):
        return "At Risk"
    else:
        return "Lost / Hibernating"
```

### 1.5 Edge Cases

| Edge Case | Handling |
|-----------|----------|
| **Single-order customers** | F=1 by definition; segment depends on R and M |
| **Very high spenders with few orders** | High M, low F → may map to "Need Attention" or "At Risk" depending on R |
| **Quintile ties** (many customers with same value) | `pd.qcut(..., duplicates='drop')` to handle ties; fallback to rank-based if needed |
| **Customers with only cancellations** | Excluded — no valid orders, no RFM score |

---

## 2. Churn Label Logic

### 2.1 Churn Definition

> **A customer has churned if they have NOT made any purchase within a defined inactivity window after their last observed purchase, measured from the snapshot date.**

This is a **binary label** for supervised classification:

| Label | Value | Condition |
|-------|-------|-----------|
| **Not Churned** | `0` | Customer made at least 1 purchase in the **evaluation period** |
| **Churned** | `1` | Customer made **zero** purchases in the **evaluation period** |

### 2.2 Temporal Split Design

To create the churn label without data leakage, we split the 24-month timeline into two windows:

```
|<------------ Observation Period ------------->|<--- Evaluation Period --->|
|  Dec 2009 ──────────────────── Jun 2011       |  Jul 2011 ─── Dec 2011   |
|  Features computed from this period           |  Label derived from here  |
|  (~18 months)                                 |  (~6 months)              |
```

| Period | Start | End | Duration | Purpose |
|--------|-------|-----|----------|---------|
| **Observation** | 1 Dec 2009 | 30 Jun 2011 | ~18 months | Compute RFM, features |
| **Evaluation** | 1 Jul 2011 | 4 Dec 2011 | ~5 months | Determine churn label |

**Churn label:**

```python
OBSERVATION_END = datetime(2011, 6, 30)
EVALUATION_START = datetime(2011, 7, 1)

# For each customer:
last_purchase_in_eval = max(InvoiceDate) where InvoiceDate >= EVALUATION_START

churn_label = 1 if (customer has NO purchases in evaluation period) else 0
```

### 2.3 Why 6-Month Evaluation Window?

| Consideration | Reasoning |
|---------------|-----------|
| **Business cycle** | Retail customers may have seasonal patterns (Christmas, etc.) — 6 months captures at least one major season |
| **Dataset length** | With ~24 months of data, 18/6 split gives sufficient observation data for features |
| **Industry standard** | 3–6 months is standard for B2C retail churn definitions |
| **Balance** | Shorter windows (e.g., 30 days) would label too many as churned; longer windows reduce training data |

### 2.4 Expected Class Distribution

Based on the dataset characteristics (many one-time buyers), we expect:

| Class | Expected % | Reasoning |
|-------|-----------|-----------| 
| **Churned (1)** | ~60–70% | Many customers are infrequent / one-time buyers |
| **Not Churned (0)** | ~30–40% | Loyal repeat customers who persist into evaluation period |

> **Imbalanced dataset** → must handle in model training (see §4.4).

### 2.5 Alternative Churn Definitions Considered

| Alternative | Why Not Used |
|-------------|-------------|
| **Days since last purchase > X** | Static threshold doesn't account for purchase frequency differences |
| **Purchase frequency drop > 50%** | Complex to compute, requires stable baseline for each customer |
| **RFM score < threshold** | Circular — using RFM to define churn would bias the model |

---

## 3. Feature Engineering Plan

### 3.1 Feature Categories

All features are computed from the **observation period** only (Dec 2009 – Jun 2011) to prevent data leakage.

#### 3.1.1 RFM Core Features

| Feature | Description | Type |
|---------|-------------|------|
| `recency_days` | Days since last purchase to `OBSERVATION_END` | int |
| `frequency` | Count of distinct invoices | int |
| `monetary` | Total revenue (`Quantity × Price`) | float |
| `r_score` | Recency quintile score (1–5) | int |
| `f_score` | Frequency quintile score (1–5) | int |
| `m_score` | Monetary quintile score (1–5) | int |
| `rfm_segment` | Categorical segment label | string |

#### 3.1.2 Behavioral Features

| Feature | Description | Type |
|---------|-------------|------|
| `avg_order_value` (AOV) | `monetary / frequency` | float |
| `avg_basket_size` | Avg number of items per order | float |
| `avg_unit_price` | Avg price per item purchased | float |
| `total_quantity` | Total items purchased | int |
| `unique_products` | Count of distinct `StockCode` | int |
| `unique_categories` | Approximate product category count | int |

#### 3.1.3 Temporal Features

| Feature | Description | Type |
|---------|-------------|------|
| `tenure_days` | Days between first and last purchase | int |
| `avg_days_between_orders` | Mean inter-purchase interval | float |
| `std_days_between_orders` | Std dev of inter-purchase interval (regularity) | float |
| `days_since_first_purchase` | `OBSERVATION_END - first_purchase_date` | int |
| `order_trend` | Slope of order-count per month (increasing/decreasing) | float |
| `is_one_time_buyer` | 1 if `frequency = 1`, else 0 | binary |

#### 3.1.4 Engagement Features

| Feature | Description | Type |
|---------|-------------|------|
| `cancellation_rate` | `cancel_orders / total_orders` | float |
| `return_quantity_rate` | `abs(negative_qty) / total_qty` | float |
| `weekend_purchase_ratio` | Fraction of orders placed on weekends | float |
| `distinct_countries` | Number of countries customer ordered from | int |

#### 3.1.5 Monetary Pattern Features

| Feature | Description | Type |
|---------|-------------|------|
| `ltv` (Lifetime Value) | Same as `monetary` for observation period | float |
| `monetary_trend` | Slope of monthly revenue (growing/shrinking) | float |
| `max_single_order_value` | Largest single order value | float |
| `min_single_order_value` | Smallest single order value | float |

### 3.2 Feature Summary

| Category | Count | Key Features |
|----------|-------|-------------|
| RFM Core | 7 | R, F, M scores + segment |
| Behavioral | 6 | AOV, basket size, product diversity |
| Temporal | 6 | Tenure, order gaps, trend |
| Engagement | 4 | Cancellation rate, weekend ratio |
| Monetary Pattern | 4 | LTV, trends, min/max orders |
| **Total** | **~27** | |

### 3.3 Feature Engineering Pipeline

```
fact_transactions (Gold layer)
    │
    ├── Aggregate per customer (observation period only)
    │   ├── RFM core: last_date, count(invoice), sum(qty*price)
    │   ├── Behavioral: avg basket, unique products
    │   ├── Temporal: first_date, inter-purchase gaps
    │   └── Engagement: cancel count, return qty
    │
    ├── Compute derived features
    │   ├── Quintile scores (R, F, M)
    │   ├── Ratios (AOV, cancel rate)
    │   └── Trends (order_trend, monetary_trend via linear regression slope)
    │
    └── Output: mart_customer_features (one row per customer)
```

---

## 4. Candidate Models

### 4.1 Model Selection Strategy

We follow a **two-model approach** as specified in the project plan:

| Model | Role | Why |
|-------|------|-----|
| **Logistic Regression (LR)** | Baseline | Interpretable, fast, establishes performance floor |
| **XGBoost** | Primary | Handles non-linearity, feature interactions, typically best for tabular data |

### 4.2 Logistic Regression (Baseline)

| Aspect | Detail |
|--------|--------|
| **Library** | `sklearn.linear_model.LogisticRegression` |
| **Preprocessing** | StandardScaler for numerical features; OneHotEncoder for categorical |
| **Regularization** | L2 (Ridge) default; search over `C = [0.01, 0.1, 1, 10]` |
| **Class weight** | `class_weight='balanced'` to handle imbalance |
| **Strengths** | Fully interpretable coefficients, fast training, strong baseline |
| **Weaknesses** | Cannot capture feature interactions or non-linear patterns |

### 4.3 XGBoost (Primary)

| Aspect | Detail |
|--------|--------|
| **Library** | `xgboost.XGBClassifier` |
| **Key hyperparameters** | `max_depth: [3, 5, 7]`, `n_estimators: [100, 200, 300]`, `learning_rate: [0.01, 0.05, 0.1]`, `subsample: [0.7, 0.8, 1.0]`, `colsample_bytree: [0.7, 0.8, 1.0]` |
| **Imbalance handling** | `scale_pos_weight = count(class_0) / count(class_1)` |
| **Early stopping** | `early_stopping_rounds=20` on validation AUC |
| **Strengths** | Handles non-linearity, feature interactions, missing values, built-in regularization |
| **Weaknesses** | Less interpretable (mitigated by SHAP in S4) |

### 4.4 Handling Class Imbalance

| Technique | Applied To | Description |
|-----------|-----------|-------------|
| **Class weights** | LR | `class_weight='balanced'` |
| **scale_pos_weight** | XGBoost | Ratio of negative to positive class |
| **Stratified splits** | Both | `StratifiedKFold` ensures each fold has same class ratio |
| **Threshold tuning** | Both | Optimize classification threshold for business objective (see §5) |

> **Note:** We do NOT use SMOTE/oversampling initially. Class weights are simpler and avoid synthetic data artifacts. If results are poor, SMOTE can be added as an iteration.

### 4.5 Cross-Validation Strategy

```
5-Fold Stratified Cross-Validation
┌─────────────────────────────────────────┐
│ Fold 1: [====TEST====][=====TRAIN======]│
│ Fold 2: [=====TRAIN===][===TEST===][===]│
│ Fold 3: [===TRAIN===][===TEST===][=====]│
│ Fold 4: [=====TRAIN=======][===TEST===] │
│ Fold 5: [====TRAIN=========][===TEST==] │
└─────────────────────────────────────────┘

Report: Mean ± Std for each metric across folds
```

| Parameter | Value |
|-----------|-------|
| Method | `StratifiedKFold(n_splits=5, shuffle=True, random_state=42)` |
| Hyperparameter search | `GridSearchCV` or `RandomizedSearchCV` on training folds |
| Final evaluation | Hold-out test set (20% stratified split before CV) |

### 4.6 Training Pipeline

```
mart_customer_features
    │
    ├── Train/Test Split (80/20, stratified)
    │
    ├── Preprocessing Pipeline (sklearn Pipeline)
    │   ├── Numerical: SimpleImputer(median) → StandardScaler
    │   └── Categorical: SimpleImputer(most_frequent) → OneHotEncoder
    │
    ├── Model 1: LogisticRegression (baseline)
    │   └── GridSearchCV (C, penalty)
    │
    ├── Model 2: XGBClassifier (primary)
    │   └── RandomizedSearchCV (depth, estimators, lr, subsample)
    │
    ├── Evaluation on Test Set
    │   ├── AUC-ROC, Precision, Recall, F1
    │   ├── Confusion Matrix
    │   └── Threshold Optimization (Precision-Recall curve)
    │
    └── MLflow Logging
        ├── Parameters, metrics, artifacts
        └── Model registry (best model)
```

---

## 5. Evaluation Metrics & Thresholds

### 5.1 Primary Metrics

| Metric | Formula | Why It Matters | Target |
|--------|---------|---------------|--------|
| **AUC-ROC** | Area under ROC curve | Overall discriminative power, threshold-independent | **≥ 0.80** (QA gate) |
| **Precision** | TP / (TP + FP) | Of predicted churners, how many actually churned? | ≥ 0.70 |
| **Recall** | TP / (TP + FN) | Of actual churners, how many did we catch? | ≥ 0.75 |
| **F1-Score** | 2 × (P × R) / (P + R) | Harmonic mean — balanced precision/recall | ≥ 0.72 |

### 5.2 Secondary Metrics

| Metric | Purpose |
|--------|---------|
| **Precision-Recall AUC** | Better than ROC-AUC for imbalanced datasets |
| **Log Loss** | Calibration quality of predicted probabilities |
| **Confusion Matrix** | Visual understanding of TP/FP/TN/FN |
| **Brier Score** | Probability calibration accuracy |

### 5.3 Threshold Optimization

The default threshold of `0.5` is rarely optimal for imbalanced data. We will:

1. Plot the **Precision-Recall curve**
2. Find the threshold that maximizes **F1-score** (or a business-specified precision/recall trade-off)
3. Report results at both `0.5` and the optimized threshold

```python
from sklearn.metrics import precision_recall_curve

precisions, recalls, thresholds = precision_recall_curve(y_test, y_proba)
f1_scores = 2 * (precisions * recalls) / (precisions + recalls + 1e-8)
optimal_threshold = thresholds[f1_scores.argmax()]
```

### 5.4 Business Context for Metrics

| Scenario | Priority | Threshold Strategy |
|----------|----------|-------------------|
| **Retention campaign (email/discount)** | High Recall | Lower threshold → catch more churners, accept some false positives |
| **Expensive intervention (phone call/gift)** | High Precision | Higher threshold → only target customers we're confident will churn |
| **General scoring** | Balanced (F1) | Optimized threshold from PR curve |

### 5.5 Quality Gate (QA Requirement)

From the project plan (QA role):

> **AUC gate > 0.80** — model must achieve AUC-ROC ≥ 0.80 on the held-out test set to pass validation.

If the gate is not met:
1. Review feature engineering (add/remove features)
2. Try feature selection (remove noise)
3. Adjust hyperparameter search space
4. Consider additional models (Random Forest, LightGBM) as fallback

---

## 6. Target Metrics Summary

### 6.1 RFM Metrics (S2 Deliverable)

| Metric | Description | Target |
|--------|-------------|--------|
| Segment coverage | All customers assigned to exactly one segment | 100% |
| Revenue reconciliation | Sum of segment revenues = total valid revenue | Δ < 0.01% |
| Segment count | 8 meaningful segments with non-zero membership | 8/8 populated |
| Champions % | Expected top-tier percentage | 5–15% of customers |
| Lost % | Expected bottom-tier percentage | 15–30% of customers |

### 6.2 Churn Model Metrics (S3 Deliverable)

| Metric | Target | Hard Gate |
|--------|--------|-----------|
| AUC-ROC | ≥ 0.80 | Yes (QA gate) |
| Precision | ≥ 0.70 | No |
| Recall | ≥ 0.75 | No |
| F1-Score | ≥ 0.72 | No |
| Cross-validation stability | Std(AUC) < 0.03 across folds | No |

### 6.3 Batch Scoring Output (S3 Deliverable)

| Output Column | Type | Description |
|---------------|------|-------------|
| `customer_id` | string | Unique customer identifier |
| `churn_probability` | float [0, 1] | Model-predicted probability of churn |
| `churn_flag` | int {0, 1} | Binary label at optimized threshold |
| `rfm_segment` | string | RFM segment label |
| `risk_tier` | string | `High / Medium / Low` based on probability buckets |

### 6.4 Explainability Metrics (S4 Deliverable)

| Deliverable | Method | Description |
|-------------|--------|-------------|
| Top churn drivers | SHAP (global) | Top 10 features by mean absolute SHAP value |
| Per-customer explanation | SHAP (local) | Waterfall plot for individual predictions |
| K-Means clusters | Elbow + Silhouette | Behavior-based segments (k=3–8, selected by silhouette score) |

---

*Document maintained by Phúc Nhân Nguyễn (MODEL). Updates tracked in Git.*
