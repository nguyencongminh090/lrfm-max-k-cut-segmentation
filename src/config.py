"""Central configuration for the LRFM + max-k-cut customer segmentation project.

Baseline = Corrêa Vianna Filho, de Lima & Kleina (2026), "RFM model customer
segmentation from a graph theory perspective", Quality & Quantity.
Our contribution = extend the RFM score vector to LRFM (add Length / tenure)
and re-run the same max-k-cut pipeline, then compare against the RFM baseline.
"""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"
TABLES = RESULTS / "tables"

# Online Retail II source file (download from UCI dataset 502).
# The UCI archive ships an .xlsx with two sheets (2009-2010, 2010-2011).
RAW_RETAIL_FILE = DATA_RAW / "online_retail_II.xlsx"

# SQLite relational layer (star schema + customer_rfml). SQL is the source of
# truth for R/F/M/L values and scores; Python reads customer_rfml for modeling.
SQLITE_DB = DATA_PROCESSED / "retail.db"

# ---------------------------------------------------------------------------
# RFM / LRFM scoring
# ---------------------------------------------------------------------------
# Number of quantile bins per variable. Paper uses T = 5 (quintiles).
T = 5

# Variables to score. "RFM" reproduces the baseline; "LRFM" is our extension.
#   R = Recency, F = Frequency, M = Monetary, L = Length (tenure)
# NOTE: with q variables and T bins, the reduced graph has at most T**q vertices.
#   RFM  -> T**3 = 125 ;  LRFM -> T**4 = 625  (still bounded, still tractable)
RFM_VARS = ["R", "F", "M"]
LRFM_VARS = ["L", "R", "F", "M"]

# For each variable, does a LARGER raw value mean a BETTER (higher) score?
#   Recency: a smaller gap since last purchase is better -> invert.
#   Frequency / Monetary / Length: larger is better.
HIGHER_IS_BETTER = {
    "R": False,   # raw recency in days; fewer days = better
    "F": True,
    "M": True,
    "L": True,    # longer relationship (tenure) = better
}

# ---------------------------------------------------------------------------
# max-k-cut
# ---------------------------------------------------------------------------
K_RANGE = range(2, 11)          # paper sweeps k = 2..10
GUROBI_TIME_LIMIT = 7200        # seconds, matches the paper's 2-hour cap
DISTANCE = "manhattan"          # edge weight metric between score vectors

# Solver backend: "local" (our from-scratch heuristic, no license -- DEFAULT),
# "gurobi" (exact, needs a real license), or "cbc" (exact open-source, slow).
SOLVER = "local"
LOCAL_RESTARTS = 200            # multi-start restarts for the local-search solver
KL_SWEEPS = 2                   # Kernighan-Lin pairwise-swap passes per round (0 disables)

# Metric used by the silhouette index (sklearn). Paper reports silhouette on
# the score vectors; euclidean is sklearn's default. Keep configurable.
SILHOUETTE_METRIC = "euclidean"

RANDOM_SEED = 42
