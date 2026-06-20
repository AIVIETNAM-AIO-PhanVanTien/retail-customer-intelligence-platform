"""Sklearn preprocessing pipeline for XGBoost.

Tree-based models only need median imputation — no scaling or
log transforms required (XGBoost handles skew natively).
"""

from __future__ import annotations

from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline


def build_tree_preprocessor() -> Pipeline:
    """Median imputer for tree-based models (no scaling needed)."""
    return Pipeline(
        steps=[("imputer", SimpleImputer(strategy="median"))]
    )
