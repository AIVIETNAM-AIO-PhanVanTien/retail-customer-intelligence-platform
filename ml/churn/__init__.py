"""Churn prediction subpackage (XGBoost).

Shared modules (feature matrix, config, artifact IO) live one level up in
``ml/`` so the upcoming ``ml/clustering`` package can reuse them.

Public API:
    from ml.churn.train import train_and_log
    from ml.churn.evaluate import evaluate_model, find_optimal_threshold
    from ml.churn.score import batch_score, save_scores
    from ml.churn.pipeline import run_train_pipeline, run_score_pipeline
    from ml.churn.explain import compute_shap_values, global_shap_importance
"""
