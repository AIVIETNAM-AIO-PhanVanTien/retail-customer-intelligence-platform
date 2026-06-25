"""ML package — customer intelligence models.

Shared modules live here; task-specific code lives in subpackages.

Shared:
    from ml.features import build_feature_matrix
    from ml.config import FEATURE_COLUMNS
    from ml.artifacts import save_model_artifacts, load_model_artifacts

Churn (XGBoost):
    from ml.churn.train import train_and_log
    from ml.churn.evaluate import evaluate_model, find_optimal_threshold
    from ml.churn.score import batch_score, save_scores
    from ml.churn.pipeline import run_train_pipeline, run_score_pipeline
    from ml.churn.explain import compute_shap_values, global_shap_importance

Clustering (K-Means):
    from ml.clustering.pipeline import run_clustering_pipeline
    from ml.clustering.train import train_kmeans, find_optimal_k
    from ml.clustering.profile import build_cluster_profiles
"""
