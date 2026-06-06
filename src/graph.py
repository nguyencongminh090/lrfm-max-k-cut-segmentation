"""Graph construction, reduction (Procedure 1) and solution lift-back (Procedure 2).

Baseline paper, Sec. 2.2 / 3.1 / 3.2:
  * Each customer is a vertex; edge weight w_ij = Manhattan distance between the
    customers' score vectors. Identical scores => w = 0 => no edge.
  * Procedure 1 merges all customers sharing a score vector into ONE super-vertex.
    Because every customer inside super-vertex i has the same score, and every
    customer inside super-vertex j has the same score, the merged weight is
        w'_ij = (count_i * count_j) * manhattan(score_i, score_j).
    The reduced graph has at most T**q vertices (125 for RFM, 625 for LRFM).
  * Procedure 2 lifts a reduced-graph cluster assignment back to every customer.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config


@dataclass
class ReducedGraph:
    """The reduced graph G'."""
    scores: np.ndarray          # (n', q) unique integer score vectors
    counts: np.ndarray          # (n',)   how many customers each super-vertex holds
    W: np.ndarray               # (n', n') symmetric merged edge-weight matrix
    members: list               # members[p] = list of CustomerIDs in super-vertex p
    variables: list             # column order, e.g. ["L","R","F","M"]

    @property
    def n_super(self) -> int:
        return len(self.counts)


def _pairwise(scores: np.ndarray, metric: str) -> np.ndarray:
    """Pairwise distance matrix between rows of `scores`."""
    if metric == "manhattan":
        return np.abs(scores[:, None, :] - scores[None, :, :]).sum(axis=2)
    if metric == "euclidean":
        diff = scores[:, None, :] - scores[None, :, :]
        return np.sqrt((diff ** 2).sum(axis=2))
    raise ValueError(f"unknown metric {metric!r}")


def reduce_graph(score_mat: pd.DataFrame, metric: str = config.DISTANCE) -> ReducedGraph:
    """Apply Procedure 1: collapse identical score vectors into super-vertices."""
    variables = list(score_mat.columns)
    customer_ids = score_mat.index.to_numpy()
    arr = score_mat.to_numpy()

    uniq, inverse = np.unique(arr, axis=0, return_inverse=True)
    inverse = inverse.ravel()
    counts = np.bincount(inverse)
    members = [customer_ids[inverse == p].tolist() for p in range(len(uniq))]

    d = _pairwise(uniq.astype(float), metric)
    W = (counts[:, None] * counts[None, :]) * d   # merged weights
    np.fill_diagonal(W, 0.0)
    return ReducedGraph(uniq, counts, W, members, variables)


def lift_assignment(rg: ReducedGraph, super_labels: np.ndarray) -> pd.Series:
    """Apply Procedure 2: map super-vertex cluster labels -> per-customer labels.

    `super_labels[p]` is the cluster of super-vertex p. Returns a Series indexed
    by CustomerID. Each customer inherits its super-vertex's label.
    """
    rows = []
    for p, members in enumerate(rg.members):
        for cid in members:
            rows.append((cid, int(super_labels[p])))
    s = pd.Series(dict(rows), name="cluster")
    s.index.name = "CustomerID"
    return s.sort_index()


if __name__ == "__main__":
    from .data_loader import get_clean
    from .rfm import compute_raw, add_scores, score_matrix
    vars_ = config.RFM_VARS
    sm = score_matrix(add_scores(compute_raw(get_clean()), vars_), vars_)
    rg = reduce_graph(sm)
    print(f"super-vertices (<= T**q): {rg.n_super}  | edges (nonzero): {(rg.W > 0).sum() // 2}")
