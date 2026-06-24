"""ML Pipeline entry point — CLI for Airflow or manual execution.

Usage::

    # Full training pipeline
    python -m ml.churn.pipeline --mode train

    # Scoring pipeline (uses saved model)
    python -m ml.churn.pipeline --mode score
"""

from __future__ import annotations

import argparse
import logging

import mlflow
import mlflow.sklearn
from sklearn.model_selection import train_test_split

from ml.artifacts import load_model_artifacts, save_model_artifacts
from ml.config import (
    FEATURE_COLUMNS,
    MLFLOW_EXPERIMENT_NAME,
    MLFLOW_TRACKING_URI,
    QA_AUC_GATE,
    RANDOM_STATE,
    TEST_SIZE,
)
from ml.churn.evaluate import (
    evaluate_model,
    find_optimal_threshold,
    log_evaluation_to_mlflow,
)
from ml.features import build_feature_matrix
from ml.churn.score import batch_score, save_scores
from ml.churn.train import train_and_log
from scripts.export_serving_app import export_serving_bundle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)


def run_train_pipeline() -> None:
    """Full training pipeline: features → train XGBoost → evaluate → save."""
    logger.info("=" * 60)
    logger.info("TRAIN PIPELINE START")
    logger.info("=" * 60)

    # 1. Feature engineering (train mode)
    logger.info("[1/5] Building feature matrix (train mode)...")
    model_df = build_feature_matrix(mode="train")
    X = model_df[FEATURE_COLUMNS].copy()
    y = model_df["churn"].astype(int)
    logger.info("Feature matrix: %d rows × %d features", len(X), X.shape[1])

    # 2. Train/test split
    logger.info("[2/5] Train/test split (%.0f%% test)...", TEST_SIZE * 100)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=TEST_SIZE,
        stratify=y,
        random_state=RANDOM_STATE,
    )

    # 3. Setup MLflow + Train XGBoost
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)

    with mlflow.start_run(run_name="xgboost-train") as run:
        mlflow.log_param("n_samples", len(X))
        mlflow.log_param("churn_rate", f"{y.mean():.4f}")
        mlflow.log_param("test_size", TEST_SIZE)

        logger.info("[3/5] Training XGBoost...")
        pipeline, best_params, cv_auc = train_and_log(X_train, y_train)

        # 4. Evaluate on test set
        logger.info("[4/5] Evaluating on test set...")
        test_metrics = evaluate_model(pipeline, X_test, y_test)
        optimal_threshold, threshold_metrics = find_optimal_threshold(
            pipeline, X_test, y_test
        )

        qa_passed = test_metrics["auc_roc"] >= QA_AUC_GATE
        logger.info(
            "Test AUC=%.4f | QA Gate (>=%.2f): %s",
            test_metrics["auc_roc"],
            QA_AUC_GATE,
            "PASS" if qa_passed else "FAIL",
        )

        # Log evaluation to MLflow
        log_evaluation_to_mlflow(
            "XGBoost", test_metrics, optimal_threshold, threshold_metrics
        )

        # 5. Save artifacts locally
        logger.info("[5/5] Saving model artifacts...")
        save_model_artifacts(
            model=pipeline,
            threshold=optimal_threshold,
            metrics=test_metrics,
            model_name="XGBoost",
        )

        # Batch score all customers
        features_all = build_feature_matrix(mode="score")
        scoring_df = batch_score(pipeline, features_all, optimal_threshold)
        save_scores(scoring_df)

        # Refresh the serving bundle (app/) so the Streamlit/HF Space
        # always ships the model from the latest run.
        export_serving_bundle(
            model=pipeline,
            threshold=optimal_threshold,
            metrics=test_metrics,
            run_id=run.info.run_id,
        )

    logger.info("=" * 60)
    logger.info(
        "TRAIN PIPELINE DONE — XGBoost AUC=%.4f | QA: %s",
        test_metrics["auc_roc"],
        "PASS" if qa_passed else "FAIL",
    )
    logger.info("=" * 60)


def run_score_pipeline() -> None:
    """Scoring pipeline: load model → features → predict → save."""
    logger.info("=" * 60)
    logger.info("SCORE PIPELINE START")
    logger.info("=" * 60)

    # 1. Load saved model
    logger.info("[1/3] Loading model artifacts...")
    model, metadata = load_model_artifacts()
    threshold = metadata.get("optimal_threshold", 0.5)
    model_name = metadata.get("model_name", "unknown")
    logger.info("Loaded: %s (threshold=%.3f)", model_name, threshold)

    # 2. Build features (score mode)
    logger.info("[2/3] Building feature matrix (score mode)...")
    features_df = build_feature_matrix(mode="score")
    logger.info("Features: %d customers", len(features_df))

    # 3. Score + save
    logger.info("[3/3] Batch scoring...")
    scoring_df = batch_score(model, features_df, threshold)
    path = save_scores(scoring_df)

    logger.info("=" * 60)
    logger.info("SCORE PIPELINE DONE → %s", path)
    logger.info("=" * 60)


# CLI Entry Point
def main() -> None:
    parser = argparse.ArgumentParser(description="ML Churn Pipeline")
    parser.add_argument(
        "--mode",
        choices=["train", "score"],
        required=True,
        help="'train' = full training pipeline; 'score' = batch prediction",
    )
    args = parser.parse_args()

    if args.mode == "train":
        run_train_pipeline()
    else:
        run_score_pipeline()


if __name__ == "__main__":
    main()
