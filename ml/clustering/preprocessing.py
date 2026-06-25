"""Preprocessing pipeline for K-Means clustering.

K-Means uses Euclidean distance, so features MUST be scaled.
Skewed features get log1p before scaling to reduce outlier impact.
"""

from __future__ import annotations

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from ml.config import FEATURE_COLUMNS, SKEWED_FEATURES


def build_clustering_preprocessor(
    feature_columns: list[str] | None = None,
    skewed_features: list[str] | None = None,
) -> ColumnTransformer:
    """Build a preprocessing pipeline for clustering.

    Two branches via ColumnTransformer:
    - Skewed features: median impute → log1p → StandardScaler
    - Non-skewed features: median impute → StandardScaler

    Returns a *unfitted* ColumnTransformer.
    """
    features = feature_columns or FEATURE_COLUMNS
    skewed = skewed_features or SKEWED_FEATURES

    skewed_cols = [f for f in features if f in skewed]
    non_skewed_cols = [f for f in features if f not in skewed]

    skewed_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("log1p", FunctionTransformer(np.log1p, validate=True)),
        ("scaler", StandardScaler()),
    ])

    non_skewed_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])

    return ColumnTransformer(
        transformers=[
            ("skewed", skewed_pipe, skewed_cols),
            ("non_skewed", non_skewed_pipe, non_skewed_cols),
        ],
        remainder="drop",
    )
