"""CLI entry point: run baseline (RFM) and/or extended (LRFM) experiments.

Examples
--------
    python run.py --mode baseline          # reproduce the paper (RFM)
    python run.py --mode extended          # our LRFM contribution
    python run.py --mode both              # both, side by side (default)
    python run.py --mode both --kmax 6     # restrict k sweep to 2..6
"""
from __future__ import annotations

import argparse

from src import config
from src.pipeline import run_experiment
from src.evaluate import sweep_table


def main() -> None:
    p = argparse.ArgumentParser(description="LRFM + max-k-cut segmentation")
    p.add_argument("--mode", choices=["baseline", "extended", "both"], default="both")
    p.add_argument("--kmin", type=int, default=2)
    p.add_argument("--kmax", type=int, default=10)
    p.add_argument("--time-limit", type=int, default=config.GUROBI_TIME_LIMIT)
    args = p.parse_args()

    k_range = range(args.kmin, args.kmax + 1)

    if args.mode in ("baseline", "both"):
        print("\n=== BASELINE: RFM + max-k-cut ===")
        base = run_experiment(config.RFM_VARS, k_range, args.time_limit)
        print(sweep_table(base.silhouette))

    if args.mode in ("extended", "both"):
        print("\n=== EXTENDED: LRFM + max-k-cut ===")
        ext = run_experiment(config.LRFM_VARS, k_range, args.time_limit)
        print(sweep_table(ext.silhouette))


if __name__ == "__main__":
    main()
