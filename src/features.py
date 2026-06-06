"""Read the SQL source-of-truth (customer_rfml) into pandas for modeling.

SQL owns R/F/M/L values and scores (see src/build_db.py). The graph/clustering
stage consumes the integer score matrix returned here. This replaces the
ad-hoc scoring in src/rfm.py for the real pipeline.
"""
from __future__ import annotations

import sqlite3
import numpy as np
import pandas as pd

from . import config


def load_customer_rfml() -> pd.DataFrame:
    """Full customer_rfml table indexed by CustomerID (raw values + scores)."""
    con = sqlite3.connect(config.SQLITE_DB)
    try:
        df = pd.read_sql_query("SELECT * FROM customer_rfml", con, index_col="customer_id")
    finally:
        con.close()
    df.index.name = "CustomerID"
    return df


def score_matrix(variables=None) -> pd.DataFrame:
    """Integer score matrix (columns in `variables` order) for graph construction.

    variables: subset/order of ["L","R","F","M"]. Defaults to LRFM.
        RFM_VARS  -> reproduces the baseline.
        LRFM_VARS -> our extension.
    """
    variables = variables or config.LRFM_VARS
    df = load_customer_rfml()
    cols = [f"{v.lower()}_score" for v in variables]
    sm = df[cols].copy()
    sm.columns = list(variables)
    return sm


def assign_segment(df: pd.DataFrame) -> pd.DataFrame:
    """Add `fm` and named RFM `segment` columns (mirrors sql/analysis.sql A2).

    Standard RFM grid on R-score and a combined FM-score, first match wins.
    """
    df = df.copy()
    df["fm"] = ((df["f_score"] + df["m_score"]) / 2).round().astype(int)
    r, fm = df["r_score"], df["fm"]
    conds = [
        (r >= 4) & (fm >= 4),
        (r >= 3) & (fm >= 3),
        (r >= 4) & (fm <= 2),
        (r == 3) & (fm <= 2),
        (r == 2) & (fm >= 3),
        (r == 1) & (fm >= 4),
        (r == 1) & (fm == 3),
        (r <= 2) & (fm <= 2),
    ]
    names = ["Champions", "Loyal Customers", "New / Promising", "Potential Loyalist",
             "At Risk", "Cannot Lose Them", "At Risk", "Hibernating / Lost"]
    df["segment"] = np.select(conds, names, default="Others")
    return df


if __name__ == "__main__":
    for vs in (config.RFM_VARS, config.LRFM_VARS):
        sm = score_matrix(vs)
        print(f"{''.join(vs):5} matrix: {sm.shape}  distinct cells: {sm.drop_duplicates().shape[0]}")
