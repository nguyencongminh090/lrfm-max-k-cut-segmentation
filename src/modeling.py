"""Stage 3 - Modeling: RFM baseline vs LRFM via max-k-cut, with comparison.

- Runs the SAME pipeline for RFM (reproduce the graph paper) and LRFM (our extension).
- Compares the silhouette sweep (k=2..10) to the paper's reported max-k-cut values.
- Profiles the segments (raw R/F/M/L per cluster) and ranks loyalty (Cheng & Chen).
Writes results/tables/stage3_modeling_report.md and results/figures/stage3_silhouette.png.

Run:  python -m src.modeling
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from . import config
from .pipeline import run_experiment
from .evaluate import profile_clusters, loyalty_ranking
from .viz_style import set_style

# max-k-cut silhouettes reported in the graph paper (Table 6) for the same dataset
PAPER_MAXKCUT = {2: 0.46, 3: 0.35, 4: 0.40, 5: 0.35,
                 6: 0.29, 7: 0.31, 8: 0.32, 9: 0.34, 10: 0.36}
REPORT = config.TABLES / "stage3_modeling_report.md"
_lines: list[str] = []


def out(s="") -> None:
    print(s)
    _lines.append(str(s))


def _best_k(exp) -> int:
    return max(exp.silhouette, key=exp.silhouette.get)


def main() -> None:
    set_style()
    out("# Stage 3 - Modeling report (RFM baseline vs LRFM, max-k-cut)\n")

    out("## Running RFM baseline")
    base = run_experiment(config.RFM_VARS)
    out("\n## Running LRFM extension")
    ext = run_experiment(config.LRFM_VARS)

    ks = list(config.K_RANGE)
    cmp = pd.DataFrame({
        "k": ks,
        "RFM_ours": [round(base.silhouette[k], 4) for k in ks],
        "paper_maxkcut": [PAPER_MAXKCUT[k] for k in ks],
        "LRFM_ours": [round(ext.silhouette[k], 4) for k in ks],
    }).set_index("k")
    out("\n## Silhouette comparison (k = 2..10)")
    out(cmp.to_string())
    out(f"\n- reduced-graph vertices: RFM={base.n_super}, LRFM={ext.n_super}")
    out(f"- best k by silhouette: RFM -> {_best_k(base)} ({base.silhouette[_best_k(base)]:.3f}), "
        f"LRFM -> {_best_k(ext)} ({ext.silhouette[_best_k(ext)]:.3f})")

    # figure
    config.FIGURES.mkdir(parents=True, exist_ok=True)
    fig, a = plt.subplots(figsize=(7, 4.5))
    a.plot(ks, cmp["RFM_ours"], "o-", label="RFM (ours)")
    a.plot(ks, cmp["paper_maxkcut"], "s--", label="max-k-cut (paper)")
    a.plot(ks, cmp["LRFM_ours"], "^-", label="LRFM (ours)")
    a.set_xlabel("number of clusters k"); a.set_ylabel("silhouette index")
    a.set_title("Silhouette: RFM vs LRFM vs paper"); a.legend(); a.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(config.FIGURES / "stage3_silhouette.png", dpi=120)
    plt.close(fig)
    out("- saved results/figures/stage3_silhouette.png")

    # business profiles at k=4 (paper's business choice) for both models
    for name, exp in [("RFM", base), ("LRFM", ext)]:
        k = 4
        out(f"\n## {name} business profile at k={k}")
        prof = profile_clusters(exp.raw, exp.labels[k], variables=exp.variables)
        out(prof.to_string(float_format=lambda x: f"{x:,.1f}"))
        loy = loyalty_ranking(exp.scored, exp.labels[k], variables=exp.variables)
        out("\nloyalty ranking (Cheng & Chen distance):")
        out(loy[["distance", "rank"]].to_string(float_format=lambda x: f"{x:,.3f}"))

    config.TABLES.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(_lines))
    print(f"\n>>> report written to {REPORT}")


if __name__ == "__main__":
    main()
