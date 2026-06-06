"""Compute RFM (baseline) and LRFM (our extension) raw values and 1..T scores.

Definitions (per the baseline paper, Sec. 4.2):
    Frequency F_i = number of transactions (invoices) of customer i
    Monetary  M_i = sum of (Quantity * Price) over customer i
    Recency   R_i = days between i's last purchase and the dataset's last date
Our extension:
    Length    L_i = days between i's first and last purchase (tenure)

Scoring: each variable is split into T quantiles and mapped to an integer 1..T,
with 1 = worst, T = best. For recency (and any HIGHER_IS_BETTER == False
variable) the order is inverted so that a better customer always gets a higher
score -- this aligns all axes, exactly as the paper does for recency.
"""
from __future__ import annotations

import pandas as pd

from . import config


def compute_raw(tx: pd.DataFrame) -> pd.DataFrame:
    """Aggregate transactions -> one row per customer with raw L,R,F,M."""
    snapshot = tx["InvoiceDate"].max()
    g = tx.groupby("CustomerID")
    out = pd.DataFrame({
        "R": (snapshot - g["InvoiceDate"].max()).dt.days,
        "F": g["Invoice"].nunique(),
        "M": g["Total"].sum(),
        "L": (g["InvoiceDate"].max() - g["InvoiceDate"].min()).dt.days,
    })
    return out


def score_variable(s: pd.Series, higher_is_better: bool, T: int = config.T) -> pd.Series:
    """Map a raw column to integer scores 1..T via quantile bins.

    Uses rank-based binning (pd.qcut on the rank) to tolerate heavy ties /
    skew in the retail data. Returns ints in [1, T] where T is best.
    """
    ranks = s.rank(method="first", ascending=higher_is_better)
    bins = pd.qcut(ranks, q=T, labels=range(1, T + 1))
    return bins.astype(int)


def add_scores(raw: pd.DataFrame, variables=None, T: int = config.T) -> pd.DataFrame:
    """Append <V>_score columns for each requested variable (default: LRFM)."""
    variables = variables or config.LRFM_VARS
    out = raw.copy()
    for v in variables:
        out[f"{v}_score"] = score_variable(raw[v], config.HIGHER_IS_BETTER[v], T)
    return out


def score_matrix(scored: pd.DataFrame, variables) -> pd.DataFrame:
    """The n x q integer score matrix used to build the graph (column order = `variables`)."""
    return scored[[f"{v}_score" for v in variables]].rename(
        columns=lambda c: c.replace("_score", "")
    )


if __name__ == "__main__":
    from .data_loader import get_clean
    raw = compute_raw(get_clean())
    scored = add_scores(raw)
    print(scored.head())
    print(f"customers: {len(scored):,}")
