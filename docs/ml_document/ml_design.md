# ML Design Document

**Project:** Retail Customer Intelligence Platform
**Author:** Phúc Nhân Nguyễn (MODEL)
**Sprint:** S1 — Discovery & Onboarding
**Date:** 2026-06-17
**Status:** Draft v2.0

---

## Table of Contents

1. [Churn Label Logic](#1-churn-label-logic)
2. [Feature Engineering Plan](#2-feature-engineering-plan)
3. [Candidate Models](#3-candidate-models)
4. [Evaluation Metrics & Model Selection](#4-evaluation-metrics--model-selection)
5. [Target Metrics Summary](#5-target-metrics-summary)

---

## 1. Churn Label Logic

### 1.1 Churn Definition

> **A customer has churned if they have NOT made any purchase within a defined evaluation window, measured from the observation cutoff date.**

This is a **binary label** for supervised classification:

| Label | Value | Condition |
|-------|-------|-----------|
| **Not Churned** | `0` | Customer made at least 1 purchase in the **evaluation period** |
| **Churned** | `1` | Customer made **zero** purchases in the **evaluation period** |

### 1.2 Temporal Split Design

To create the churn label without data leakage, we split the timeline into two windows. The timestamps below are **day-shifted to the current date** — when working with the actual dataset (Dec 2009 – Dec 2011), all dates will be shifted forward so that the end of the evaluation period aligns with the current date (~June 2026).

```
|<------------ Observation Period ----------------->|<-- Evaluation Period -->|
|  ~21 months of purchase history                   |  3 months              |
|  Features computed from this period               |  Label derived here    |
```

| Period | Duration | Purpose |
|--------|----------|---------|
| **Observation** | ~21 months | Compute features (R, F, M, behavioral, temporal, etc.) |
| **Evaluation** | 3 months | Determine churn label (purchased or not) |

> **Note on day-shifting:** The original dataset spans Dec 2009 – Dec 2011. All timestamps will be shifted forward so the final transaction date aligns with the current date. This ensures the model operates on a realistic time horizon relative to "today" for inference purposes. The relative durations (21-month observation, 3-month evaluation) remain unchanged regardless of the shift.

**Churn label logic:**

```python
# After day-shifting, define the cutoff
OBSERVATION_END = SHIFTED_MAX_DATE - timedelta(days=90)  # ~3 months before end
EVALUATION_START = OBSERVATION_END + timedelta(days=1)

# For each customer:
# Count purchases in [EVALUATION_START, SHIFTED_MAX_DATE]
churn_label = 1 if (customer has NO purchases in evaluation period) else 0
```

### 1.3 Why 3-Month Evaluation Window?

| Consideration | Reasoning |
|---------------|-----------|
| **Sufficient signal** | 90 days gives customers reasonable time to return if they are still active |
| **Data preservation** | A shorter evaluation window preserves more data (~21 months) for feature engineering |
| **Industry practice** | 3 months is a widely used threshold for B2C retail churn |
| **Balance** | Avoids over-labeling (30-day window) while retaining enough training data (vs. 6-month window) |

### 1.4 Expected Class Distribution

Based on the dataset characteristics (many one-time buyers), we expect:

| Class | Expected % | Reasoning |
|-------|-----------|-----------| 
| **Churned (1)** | ~60–70% | Many customers are infrequent / one-time buyers |
| **Not Churned (0)** | ~30–40% | Loyal repeat customers who persist into evaluation period |

> **Imbalanced dataset** → must handle in model training (see §3.4).

---

## 2. Feature Engineering Plan

### 2.1 Data Source: Silver Layer

All features are engineered from the **silver layer** (`stg_bronze__transactions`) during the **observation period** only to prevent data leakage.

The silver layer provides the following columns per transaction row:

| Column | Type | Description |
|--------|------|-------------|
| `invoice` | string | Invoice number |
| `stock_code` | string | Product code |
| `description` | string | Product description |
| `quantity` | int | Quantity purchased (negative for cancellations) |
| `price` | float | Unit price |
| `customer_id` | string | Customer identifier |
| `country` | string | Country of purchase |
| `is_cancellation` | bool | Whether invoice is a cancellation |
| `line_amount` | float | `quantity × price` |
| `invoice_date` | datetime | Transaction timestamp |
| `invoice_year`, `invoice_month`, etc. | int | Extracted date parts |

### 2.2 Feature Categories

#### 2.2.1 RFM Raw Features

These are the **raw** Recency, Frequency, and Monetary values — no quintile scores or segment labels.

| Feature | Description | Source Computation | Type |
|---------|-------------|-------------------|------|
| `recency_days` | Days since last purchase to `OBSERVATION_END` | `OBSERVATION_END − MAX(invoice_date)` per customer | int |
| `frequency` | Count of distinct valid invoices | `COUNT(DISTINCT invoice) WHERE is_cancellation = false` | int |
| `monetary` | Total revenue from valid transactions | `SUM(line_amount) WHERE is_cancellation = false` | float |
| `frequency_last_30d` | Invoices in last 30 days | Frequency limited to `OBSERVATION_END - 30 days` | int |
| `frequency_last_90d` | Invoices in last 90 days | Frequency limited to `OBSERVATION_END - 90 days` | int |
| `monetary_last_90d` | Revenue in last 90 days | Monetary limited to `OBSERVATION_END - 90 days` | float |

> **Rationale for raw R/F/M only:** Quintile scores (`r_score`, `f_score`, `m_score`) and `rfm_segment` are excluded because they are discretized transformations of the raw values. Using raw continuous values preserves the full information and avoids information loss from binning. Tree-based models (Random Forest, XGBoost) can capture non-linear patterns from raw values directly.

#### 2.2.2 Behavioral Features

| Feature | Description | Source Computation | Type |
|---------|-------------|-------------------|------|
| `avg_order_value` | Average revenue per order | `monetary / frequency` | float |
| `avg_basket_size` | Avg items per order | `SUM(quantity) / COUNT(DISTINCT invoice)` (valid only) | float |
| `avg_unit_price` | Avg price per item | `SUM(price × quantity) / SUM(quantity)` (valid only) | float |
| `total_quantity` | Total items purchased | `SUM(quantity) WHERE is_cancellation = false` | int |
| `unique_products` | Distinct products purchased | `COUNT(DISTINCT stock_code)` | int |
| `product_diversity_trend` | Trend of unique products over time | Unique products in last 90d / total unique products | float |

#### 2.2.3 Temporal Features

| Feature | Description | Source Computation | Type |
|---------|-------------|-------------------|------|
| `tenure_days` | Days between first and last purchase | `MAX(invoice_date) − MIN(invoice_date)` | int |
| `avg_days_between_orders` | Mean inter-purchase interval | Mean of gaps between consecutive `invoice_date` values | float |
| `std_days_between_orders` | Regularity of purchases | Std dev of inter-purchase gaps | float |
| `days_since_first_purchase` | Customer lifetime span | `OBSERVATION_END − MIN(invoice_date)` | int |
| `is_one_time_buyer` | Single-purchase customer flag | `1 if frequency = 1 else 0` | binary |
| `overdue_ratio` | Ratio of recency to avg order gap | `recency_days / avg_days_between_orders` | float |
| `purchase_regularity` | Coefficient of variation of order gaps | `std_days_between_orders / avg_days_between_orders` | float |
| `recency_one_time` | Recency applied to one-time buyers | `recency_days` if `is_one_time_buyer` else 0 | int |

#### 2.2.4 Engagement Features

| Feature | Description | Source Computation | Type |
|---------|-------------|-------------------|------|
| `cancellation_rate` | Proportion of cancelled orders | `COUNT(invoice WHERE is_cancellation) / COUNT(DISTINCT invoice)` | float |
| `return_quantity_rate` | Proportion of returned items | `ABS(SUM(quantity WHERE quantity < 0)) / SUM(quantity WHERE quantity > 0)` | float |
| `weekend_purchase_ratio` | Weekend shopping tendency | `COUNT(invoice WHERE invoice_day_of_week IN (6,7)) / COUNT(invoice)` | float |

#### 2.2.5 Monetary Pattern & Velocity Features

| Feature | Description | Source Computation | Type |
|---------|-------------|-------------------|------|
| `monetary_trend` | Spending direction over time | Linear regression slope of monthly revenue | float |
| `max_single_order_value` | Largest single order | `MAX(SUM(line_amount) GROUP BY invoice)` | float |
| `min_single_order_value` | Smallest single order | `MIN(SUM(line_amount) GROUP BY invoice)` | float |
| `ratio_frequency_90d` | Buying velocity | `frequency_last_90d / frequency` | float |
| `velocity_ratio_180d` | Velocity in 180d vs overall | `(frequency_last_180d / 180) / (frequency / tenure_days)` | float |
| `spending_recency_ratio` | Recent spending vs total | `monetary_last_90d / monetary` | float |
| `velocity_ratio_30d_90d` | Short vs medium term velocity | `frequency_last_30d / frequency_last_90d` | float |
| `monetary_acceleration` | Change in spending rate | Compare recent AOV to historical AOV | float |

#### 2.2.6 Categorical Features

| Feature | Description | Source Computation | Type |
|---------|-------------|-------------------|------|
| `is_uk` | Is customer from United Kingdom | `1 if country == 'United Kingdom' else 0` | binary |

### 2.3 Feature Summary

| Category | Count | Key Features |
|----------|-------|-------------|
| RFM Raw & Windowed | 6 | recency_days, frequency, monetary, freq_last_30d |
| Behavioral | 6 | AOV, basket size, product diversity, diversity trend |
| Temporal | 8 | Tenure, order gaps, one-time flag, overdue_ratio |
| Engagement | 3 | Cancellation rate, return rate, weekend ratio |
| Monetary Pattern & Velocity | 8 | Spending trend, velocity ratios, max/min order value |
| Categorical | 1 | is_uk flag |
| **Total** | **32** | |

### 2.4 Feature Engineering Pipeline

```
stg_bronze__transactions (Silver layer)
    │
    ├── Filter: observation period only (invoice_date <= OBSERVATION_END)
    │
    ├── Aggregate per customer_id
    │   ├── RFM raw: MAX(invoice_date), COUNT(DISTINCT invoice), SUM(line_amount)
    │   ├── Behavioral: SUM(quantity), COUNT(DISTINCT stock_code), AVG(price)
    │   ├── Temporal: MIN(invoice_date), inter-purchase gaps
    │   └── Engagement: COUNT(is_cancellation=true), SUM(negative qty)
    │
    ├── Compute derived features
    │   ├── Ratios: AOV, cancel_rate, return_qty_rate, weekend_ratio
    │   ├── Trends: monetary_trend via linear regression slope on monthly revenue
    │   └── Flags: is_one_time_buyer
    │
    └── Output: customer feature matrix (one row per customer_id)
```

---

## 3. Candidate Models

### 3.1 Model Selection Strategy

We follow a **three-model approach**: one baseline + two tree-based models for comparison.

| Model | Role | Why |
|-------|------|-----|
| **Logistic Regression (LR)** | Baseline | Interpretable, fast, establishes performance floor |
| **Random Forest (RF)** | Candidate | Robust ensemble, handles non-linearity, less prone to overfitting than single trees |
| **XGBoost** | Candidate | Gradient boosting handles feature interactions, typically best for tabular data |

### 3.2 Logistic Regression (Baseline)

| Aspect | Detail |
|--------|--------|
| **Library** | `sklearn.linear_model.LogisticRegression` |
| **Preprocessing** | Log1p transformation for highly skewed features → StandardScaler |
| **Regularization** | L2 (Ridge) default; search over `C = [0.01, 0.1, 1, 10]` |
| **Class weight** | `class_weight='balanced'` to handle imbalance |
| **Strengths** | Fully interpretable coefficients, fast training, strong baseline |
| **Weaknesses** | Cannot capture feature interactions or non-linear patterns |

### 3.3 Random Forest (Candidate)

| Aspect | Detail |
|--------|--------|
| **Library** | `sklearn.ensemble.RandomForestClassifier` |
| **Key hyperparameters** | `n_estimators: [100, 200, 300]`, `max_depth: [5, 10, 15, None]`, `min_samples_split: [2, 5, 10]`, `min_samples_leaf: [1, 2, 4]`, `max_features: ['sqrt', 'log2']` |
| **Imbalance handling** | `class_weight='balanced'` |
| **Strengths** | Robust to outliers, handles non-linearity, built-in feature importance, less prone to overfitting |
| **Weaknesses** | Slower than LR, less interpretable than LR, can underperform XGBoost on structured data |

### 3.4 XGBoost (Candidate)

| Aspect | Detail |
|--------|--------|
| **Library** | `xgboost.XGBClassifier` |
| **Key hyperparameters** | `max_depth: [3, 5, 7]`, `n_estimators: [100, 200, 300]`, `learning_rate: [0.01, 0.05, 0.1]`, `gamma: [0, 0.1, 0.5]`, `min_child_weight: [1, 3, 5]` |
| **Imbalance handling** | `scale_pos_weight = count(class_0) / count(class_1)` |
| **Early stopping** | `early_stopping_rounds=20` on validation AUC |
| **Strengths** | Handles non-linearity, feature interactions, missing values, built-in regularization |
| **Weaknesses** | Less interpretable (mitigated by SHAP in S4), more hyperparameters to tune |

### 3.5 Handling Class Imbalance

| Technique | Applied To | Description |
|-----------|-----------|-------------|
| **Class weights** | LR, RF | `class_weight='balanced'` |
| **scale_pos_weight** | XGBoost | Ratio of negative to positive class |
| **Stratified splits** | All | `StratifiedKFold` ensures each fold has same class ratio |
| **Threshold tuning** | All | Optimize classification threshold for business objective (see §4) |

> **Note:** We do NOT use SMOTE/oversampling initially. Class weights are simpler and avoid synthetic data artifacts. If results are poor, SMOTE can be added as an iteration.

### 3.6 Cross-Validation Strategy

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

### 3.7 Training Pipeline

```
customer_feature_matrix (from §2.4)
    │
    ├── Train/Test Split (80/20, stratified)
    │
    ├── Preprocessing Pipeline (sklearn Pipeline)
    │   ├── Skewed Numerical: SimpleImputer(median) → FunctionTransformer(np.log1p) → StandardScaler
    │   └── Regular Numerical: SimpleImputer(median) → StandardScaler
    │
    ├── Model 1: LogisticRegression (baseline)
    │   └── GridSearchCV (C, penalty)
    │
    ├── Model 2: RandomForestClassifier (candidate)
    │   └── RandomizedSearchCV (n_estimators, max_depth, min_samples_split, ...)
    │
    ├── Model 3: XGBClassifier (candidate)
    │   └── RandomizedSearchCV (depth, estimators, lr, subsample)
    │
    ├── Evaluation on Test Set (see §4)
    │
    └── MLflow Logging
        ├── Parameters, metrics, artifacts
        └── Model registry (best model)
```

---

## 4. Evaluation Metrics & Model Selection

### 4.1 Evaluation Metrics

Each model is evaluated on the held-out test set using the following metrics:

| Metric | Description | Why It Matters |
|--------|-------------|----------------|
| **Accuracy** | `(TP + TN) / (TP + TN + FP + FN)` | Overall correctness; reference metric (interpret with caution on imbalanced data) |
| **Classification Report** | Precision, Recall, F1-Score per class + macro/weighted avg | Detailed per-class performance breakdown |
| **Confusion Matrix** | 2×2 matrix of TP, FP, FN, TN | Visual understanding of error types and their distribution |
| **AUC-ROC** | Area under the ROC curve | Threshold-independent measure of discriminative power |

**Classification Report structure:**

```
              precision    recall  f1-score   support

   Not Churn     ...        ...      ...       ...
       Churn     ...        ...      ...       ...

    accuracy                          ...       ...
   macro avg     ...        ...      ...       ...
weighted avg     ...        ...      ...       ...
```

**Confusion Matrix structure:**

```
                  Predicted
                  Not Churn    Churn
Actual Not Churn  [   TN    |   FP   ]
       Churn      [   FN    |   TP   ]
```

### 4.2 Model Comparison Table

All models are compared side-by-side on the test set to select the best performer:

| Metric | Logistic Regression (Baseline) | Random Forest | XGBoost |
|--------|-------------------------------|---------------|---------|
| Accuracy | — | — | — |
| Precision (Churn) | — | — | — |
| Recall (Churn) | — | — | — |
| F1-Score (Churn) | — | — | — |
| AUC-ROC | — | — | — |

> Values to be filled after training. The **best model** is selected based on the highest **AUC-ROC** as the primary criterion, with **F1-Score** as the tiebreaker.

### 4.3 Model Selection Criteria

The best model is selected using the following priority:

1. **AUC-ROC ≥ 0.80** (QA gate — must pass)
2. **Highest AUC-ROC** among passing models
3. **F1-Score** as tiebreaker if AUC-ROC is similar (within 0.01)
4. **Simplicity preference**: if performance is comparable, prefer simpler models (LR > RF > XGBoost)

### 4.4 Threshold Optimization

The default threshold of `0.5` is rarely optimal for imbalanced data. We will:

1. Plot the **Precision-Recall curve** for the best model
2. Find the threshold that maximizes **F1-score**
3. Report results at both `0.5` and the optimized threshold

```python
from sklearn.metrics import precision_recall_curve

precisions, recalls, thresholds = precision_recall_curve(y_test, y_proba)
f1_scores = 2 * (precisions * recalls) / (precisions + recalls + 1e-8)
optimal_threshold = thresholds[f1_scores.argmax()]
```

### 4.5 Quality Gate (QA Requirement)

> **AUC gate > 0.80** — model must achieve AUC-ROC ≥ 0.80 on the held-out test set to pass validation.

If the gate is not met:
1. Review feature engineering (add/remove features)
2. Try feature selection (remove noise)
3. Adjust hyperparameter search space
4. Consider additional models (LightGBM, CatBoost) as fallback

---

## 5. Target Metrics Summary

### 5.1 Churn Model Metrics (S3 Deliverable)

| Metric | Target | Hard Gate |
|--------|--------|-----------|
| AUC-ROC | ≥ 0.80 | Yes (QA gate) |
| Precision (Churn) | ≥ 0.70 | No |
| Recall (Churn) | ≥ 0.75 | No |
| F1-Score (Churn) | ≥ 0.72 | No |
| Cross-validation stability | Std(AUC) < 0.03 across folds | No |

### 5.2 Batch Scoring Output (S3 Deliverable)

| Output Column | Type | Description |
|---------------|------|-------------|
| `customer_id` | string | Unique customer identifier |
| `churn_probability` | float [0, 1] | Model-predicted probability of churn |
| `churn_flag` | int {0, 1} | Binary label at optimized threshold |
| `risk_tier` | string | `High / Medium / Low` based on probability buckets |

### 5.3 Explainability Metrics (S4 Deliverable)

| Deliverable | Method | Description |
|-------------|--------|-------------|
| Top churn drivers | SHAP (global) | Top 10 features by mean absolute SHAP value |
| Per-customer explanation | SHAP (local) | Waterfall plot for individual predictions |
| K-Means clusters | Elbow + Silhouette | Behavior-based segments (k=3–8, selected by silhouette score) |

---

*Document maintained by Phúc Nhân Nguyễn (MODEL). Updates tracked in Git.*
