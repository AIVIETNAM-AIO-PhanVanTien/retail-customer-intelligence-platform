"""XGBoost churn model training with cross-validation and MLflow tracking.

Production pipeline uses XGBoost only — validated as the best-performing
model in notebook experiments (highest AUC-ROC, best F1 trade-off).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.model_selection import (
    RandomizedSearchCV,
    StratifiedKFold,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from ml.config import FEATURE_COLUMNS, RANDOM_STATE
from ml.preprocessing import build_tree_preprocessor

logger = logging.getLogger(__name__)


def train_xgboost(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    cv: StratifiedKFold | None = None,
) -> tuple[Pipeline, dict[str, Any], float]:
    """Train XGBoost with RandomizedSearchCV + early stopping.

    Parameters
    ----------
    X_train : Training feature matrix.
    y_train : Training labels.
    cv : Cross-validation splitter. Created if *None*.

    Returns
    -------
    (pipeline, best_params, cv_auc)
    """
    if cv is None:
        cv = StratifiedKFold(
            n_splits=5, shuffle=True, random_state=RANDOM_STATE
        )

    class_counts = y_train.value_counts().sort_index()
    scale_pos_weight = float(class_counts.iloc[0] / class_counts.iloc[1])

    # Hold-out split for early stopping
    X_tr, X_val, y_tr, y_val = train_test_split(
        X_train, y_train,
        test_size=0.2,
        stratify=y_train,
        random_state=RANDOM_STATE,
    )

    tree_preprocess = build_tree_preprocessor()
    X_tr_processed = tree_preprocess.fit_transform(X_tr)
    X_val_processed = tree_preprocess.transform(X_val)

    estimator = XGBClassifier(
        eval_metric=["logloss", "auc"],
        early_stopping_rounds=20,
        scale_pos_weight=scale_pos_weight,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )

    search = RandomizedSearchCV(
        estimator=estimator,
        param_distributions={
            "max_depth": [3, 5, 7],
            "n_estimators": [100, 200, 300],
            "learning_rate": [0.01, 0.05, 0.1],
            "gamma": [0, 0.1, 0.5],
            "min_child_weight": [1, 3, 5],
            "subsample": [0.7, 0.8, 1.0],
            "colsample_bytree": [0.7, 0.8, 1.0],
        },
        n_iter=50,
        scoring="roc_auc",
        cv=cv,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        refit=True,
    )

    start = time.perf_counter()
    search.fit(
        X_tr_processed,
        y_tr,
        eval_set=[(X_val_processed, y_val)],
        verbose=False,
    )
    elapsed = time.perf_counter() - start

    # Wrap best estimator in a pipeline for consistent predict interface
    pipeline = Pipeline(
        steps=[
            ("preprocess", tree_preprocess),
            ("model", search.best_estimator_),
        ]
    )

    logger.info(
        "XGBoost trained: CV AUC=%.4f, scale_pos_weight=%.2f (%.1fs)",
        search.best_score_,
        scale_pos_weight,
        elapsed,
    )
    return pipeline, search.best_params_, search.best_score_


def train_and_log(
    X_train: pd.DataFrame,
    y_train: pd.Series,
) -> tuple[Pipeline, dict[str, Any], float]:
    """Train XGBoost and log parameters/model to MLflow.

    This is the main entry point called by ``pipeline.py``.

    Returns
    -------
    (pipeline, best_params, cv_auc)
    """
    pipeline, best_params, cv_auc = train_xgboost(X_train, y_train)

    # Log to MLflow (expects an active run from pipeline.py)
    mlflow.log_params({k: str(v) for k, v in best_params.items()})
    mlflow.log_metric("cv_auc", cv_auc)
    mlflow.log_param("model_type", "XGBClassifier")
    mlflow.log_param("n_features", len(FEATURE_COLUMNS))
    mlflow.sklearn.log_model(pipeline, "xgboost-model")

    return pipeline, best_params, cv_auc
