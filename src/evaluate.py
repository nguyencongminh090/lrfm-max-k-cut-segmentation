"""Evaluation: silhouette index + business profiling of the segments.

- silhouette_for_labels: clustering quality on the score vectors (the metric the
  baseline reports; lets us draw the head-to-head Table-6 / Fig-5 comparison).
- profile_clusters: per-cluster min/mean/max of the RAW L,R,F,M values plus the
  customer count -- mirrors the paper's Tables 7 & 8.
- loyalty_ranking: Cheng & Chen (2009) loyalty class -- distance of each
  cluster's mean score vector from the origin, ranked (paper's Table 9).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import silhouette_score

from . import config


def silhouette_for_labels(score_mat: pd.DataFrame, labels: pd.Series,
                          metric: str = config.SILHOUETTE_METRIC) -> float:
    """Overall silhouette index. `labels` indexed by CustomerID (from lift)."""
    X = score_mat.loc[labels.index].to_numpy()
    if len(np.unique(labels)) < 2:
        return float("nan")
    return float(silhouette_score(X, labels.to_numpy(), metric=metric))


def profile_clusters(raw: pd.DataFrame, labels: pd.Series, variables=None) -> pd.DataFrame:
    """min / mean / max of raw variables per cluster, plus member count."""
    variables = variables or [v for v in config.LRFM_VARS if v in raw.columns]
    df = raw.loc[labels.index].copy()
    df["cluster"] = labels.values
    agg = df.groupby("cluster")[variables].agg(["min", "mean", "max"])
    agg[("count", "")] = df.groupby("cluster").size()
    return agg


def loyalty_ranking(scored: pd.DataFrame, labels: pd.Series, variables=None) -> pd.DataFrame:
    """Cheng & Chen (2009) loyalty: rank clusters by ||mean score vector||."""
    variables = variables or config.LRFM_VARS
    score_cols = [f"{v}_score" for v in variables]
    df = scored.loc[labels.index, score_cols].copy()
    df["cluster"] = labels.values
    means = df.groupby("cluster")[score_cols].mean()
    means["distance"] = np.sqrt((means[score_cols] ** 2).sum(axis=1))
    means["rank"] = means["distance"].rank(ascending=False).astype(int)
    return means.sort_values("rank")


def sweep_table(results: dict) -> pd.DataFrame:
    """Tidy a {k: silhouette} dict into a sortable comparison frame."""
    return pd.DataFrame(
        {"k": list(results), "silhouette": list(results.values())}
    ).set_index("k")
