"""K-Means customer clustering — behavior-based segmentation.

Complements rule-based RFM segmentation with unsupervised ML
that leverages the full 31-feature behavioral matrix.

    from ml.clustering.pipeline import run_clustering_pipeline
    from ml.clustering.train import train_kmeans, find_optimal_k
    from ml.clustering.profile import build_cluster_profiles
"""
