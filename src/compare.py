"""Compare OUR models against the PAPER's models (silhouette, k=2..10).

For a fair, self-consistent comparison we run every method OURSELVES on the
SAME score matrix:
    - max-k-cut (ours, from-scratch solver)
    - K-means, Ward agglomerative, GMM   (scikit-learn)
for BOTH feature sets (RFM = baseline, LRFM = our extension).

We then cross-check our RFM/max-k-cut against the values the graph paper
reported (Rungruang et al. silhouettes carried in Table 6) to confirm we
reproduce the published baseline.

Writes results/tables/comparison_report.md and results/figures/comparison_*.png.
Run:  python -m src.compare
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.cluster import KMeans, AgglomerativeClustering
from sklearn.mixture import GaussianMixture
from sklearn.metrics import silhouette_score

from . import config
from .features import score_matrix
from .graph import reduce_graph, lift_assignment
from .maxkcut import solve_maxkcut
from .viz_style import set_style

# Silhouettes reported in the graph paper (Table 6), same dataset, RFM scores.
PAPER = {
    "max-k-cut":    {2: 0.46, 3: 0.35, 4: 0.40, 5: 0.35, 6: 0.29, 7: 0.31, 8: 0.32, 9: 0.34, 10: 0.36},
    "K-means":      {2: 0.40, 3: 0.31, 4: 0.33, 5: 0.31, 6: 0.30, 7: 0.29, 8: 0.29, 9: 0.29, 10: 0.27},
    "Hierarchical": {2: 0.32, 3: 0.25, 4: 0.28, 5: 0.26, 6: 0.23, 7: 0.23, 8: 0.23, 9: 0.21, 10: 0.21},
    "GMM":          {2: 0.40, 3: 0.37, 4: 0.36, 5: 0.24, 6: 0.16, 7: 0.14, 8: 0.18, 9: 0.23, 10: 0.22},
}
REPORT = config.TABLES / "comparison_report.md"
_lines: list[str] = []


def out(s="") -> None:
    print(s)
    _lines.append(str(s))


def _maxkcut_labels(sm, k):
    rg = reduce_graph(sm)
    super_labels, _, _ = solve_maxkcut(rg, k)
    return lift_assignment(rg, super_labels).loc[sm.index].to_numpy()


def _silhouettes(sm) -> pd.DataFrame:
    """Silhouette per method per k on the given score matrix."""
    X = sm.to_numpy()
    rows = {}
    for k in config.K_RANGE:
        labs = {
            "max-k-cut": _maxkcut_labels(sm, k),
            "K-means": KMeans(k, n_init=10, random_state=config.RANDOM_SEED).fit_predict(X),
            "Ward": AgglomerativeClustering(k, linkage="ward").fit_predict(X),
            "GMM": GaussianMixture(k, random_state=config.RANDOM_SEED).fit_predict(X),
        }
        rows[k] = {m: round(silhouette_score(X, lb, metric=config.SILHOUETTE_METRIC), 4)
                   for m, lb in labs.items()}
    return pd.DataFrame(rows).T.rename_axis("k")


def main() -> None:
    set_style()
    out("# Our models vs Paper models - silhouette comparison\n")

    sm_rfm = score_matrix(config.RFM_VARS)
    sm_lrfm = score_matrix(config.LRFM_VARS)

    out("## OUR methods on RFM scores (baseline feature set)")
    rfm = _silhouettes(sm_rfm)
    out(rfm.to_string())

    out("\n## PAPER reported (Table 6, RFM scores) - validation cross-check")
    paper = pd.DataFrame(PAPER).rename_axis("k")
    out(paper.to_string())
    delta = (rfm["max-k-cut"] - paper["max-k-cut"]).abs()
    out(f"\n- our max-k-cut vs paper max-k-cut: mean |Δ silhouette| = {delta.mean():.3f} "
        f"(max {delta.max():.3f}) -> reproduction { 'CONFIRMED' if delta.mean() < 0.03 else 'CHECK'}")

    out("\n## OUR methods on LRFM scores (our extension feature set)")
    lrfm = _silhouettes(sm_lrfm)
    out(lrfm.to_string())

    # headline: our model (LRFM/max-k-cut) vs paper model (RFM/max-k-cut)
    out("\n## Headline: OUR model (LRFM/max-k-cut) vs PAPER model (RFM/max-k-cut)")
    head = pd.DataFrame({
        "paper_RFM_maxkcut": paper["max-k-cut"],
        "our_RFM_maxkcut": rfm["max-k-cut"],
        "our_LRFM_maxkcut": lrfm["max-k-cut"],
    })
    out(head.to_string())
    out(f"\n- best silhouette: paper RFM/max-k-cut = {paper['max-k-cut'].max():.2f} (k={paper['max-k-cut'].idxmax()}); "
        f"our LRFM/max-k-cut = {lrfm['max-k-cut'].max():.2f} (k={lrfm['max-k-cut'].idxmax()})")
    out("- NOTE: LRFM is expected to score LOWER on silhouette (4D vs 3D); its value "
        "is tenure-based ACTIONABILITY, not the silhouette metric (see stage3 report).")

    # figures
    config.FIGURES.mkdir(parents=True, exist_ok=True)
    ks = list(config.K_RANGE)
    fig, ax = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for m in ["max-k-cut", "K-means", "Ward", "GMM"]:
        ax[0].plot(ks, rfm[m], "o-", label=f"{m} (ours)")
    ax[0].plot(ks, [PAPER["max-k-cut"][k] for k in ks], "k--", label="max-k-cut (paper)")
    ax[0].set_title("RFM features"); ax[0].set_xlabel("k"); ax[0].set_ylabel("silhouette"); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3)
    for m in ["max-k-cut", "K-means", "Ward", "GMM"]:
        ax[1].plot(ks, lrfm[m], "o-", label=f"{m} (ours)")
    ax[1].set_title("LRFM features"); ax[1].set_xlabel("k"); ax[1].legend(fontsize=8); ax[1].grid(alpha=.3)
    fig.suptitle("Silhouette by method - RFM vs LRFM"); fig.tight_layout()
    fig.savefig(config.FIGURES / "comparison_silhouette.png", dpi=120); plt.close(fig)
    out("\n- saved results/figures/comparison_silhouette.png")

    config.TABLES.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(_lines))
    print(f"\n>>> report -> {REPORT}")


if __name__ == "__main__":
    main()
