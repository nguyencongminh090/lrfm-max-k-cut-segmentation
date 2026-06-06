"""End-to-end pipeline: data -> scores -> reduced graph -> max-k-cut -> evaluation.

Run the SAME pipeline twice and compare:
    run_experiment(variables=config.RFM_VARS)   # baseline (reproduce paper)
    run_experiment(variables=config.LRFM_VARS)  # our extension

Each call sweeps k in K_RANGE and returns the per-k silhouette plus the
cluster labels for inspection / profiling.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import config
from .features import load_customer_rfml, score_matrix as sql_score_matrix
from .graph import reduce_graph, lift_assignment
from .maxkcut import solve_maxkcut
from .evaluate import silhouette_for_labels

# raw column <-> R/F/M/L naming used by the evaluation helpers
_RAW = {"recency": "R", "frequency": "F", "monetary": "M", "length": "L"}
_SCORE = {"r_score": "R_score", "f_score": "F_score", "m_score": "M_score", "l_score": "L_score"}


@dataclass
class Experiment:
    variables: list
    raw: pd.DataFrame
    scored: pd.DataFrame
    score_mat: pd.DataFrame
    n_super: int
    silhouette: dict = field(default_factory=dict)   # k -> silhouette
    labels: dict = field(default_factory=dict)        # k -> Series(CustomerID -> cluster)
    objective: dict = field(default_factory=dict)     # k -> BQO objective


def run_experiment(variables=None, k_range=config.K_RANGE) -> Experiment:
    """Full segmentation experiment for one choice of score variables.

    Reads R/F/M/L values and scores from the SQL source of truth (customer_rfml),
    builds the reduced graph, solves max-k-cut for each k, lifts the assignment
    back to customers, and records the silhouette.
    """
    variables = variables or config.LRFM_VARS

    df = load_customer_rfml()                       # SQL source of truth
    raw = df.rename(columns=_RAW)[list(_RAW.values())]            # R,F,M,L
    scored = df.rename(columns=_SCORE)[list(_SCORE.values())]     # R_score..L_score
    sm = sql_score_matrix(variables)                # integer score matrix (cols = variables)
    rg = reduce_graph(sm)

    exp = Experiment(variables, raw, scored, sm, rg.n_super)
    for k in k_range:
        super_labels, obj, gap = solve_maxkcut(rg, k)
        labels = lift_assignment(rg, super_labels)
        exp.labels[k] = labels
        exp.objective[k] = obj
        exp.silhouette[k] = silhouette_for_labels(sm, labels)
        print(f"[{''.join(variables)}] k={k}  sil={exp.silhouette[k]:.4f}  cut={obj:,.0f}")
    return exp


if __name__ == "__main__":
    baseline = run_experiment(config.RFM_VARS)
    extended = run_experiment(config.LRFM_VARS)
