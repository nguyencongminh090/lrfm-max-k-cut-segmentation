"""Stage 4 - Data Visualization (modern, referee-friendly).

Segments are DATA-DRIVEN: the LRFM max-k-cut clusters at k=4, labelled by
Cheng & Chen (2009) loyalty rank (Low/Medium/High/Very high) - the same scheme
the baseline paper used. No arbitrary named-grid thresholds.

Figures (all standard, easy-to-read chart types):
    viz_segment_value.png        volume (% customers) vs value (% revenue) per cluster
    viz_segment_heatmap.png      cluster x (R,F,M,L) mean-score profile
    viz_segment_boxplot.png      monetary distribution per cluster (log)
    viz_segment_profile_bars.png grouped bars of R/F/M/L per cluster (replaces radar)
    viz_segment_scatter2d.png    R x M and F x M, coloured by cluster (replaces 3D; matches paper Fig 6)

Run:  python -m src.viz
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

from . import config
from .features import load_customer_rfml, score_matrix
from .graph import reduce_graph, lift_assignment
from .maxkcut import solve_maxkcut
from .viz_style import set_style, save, PALETTE, SEQ

SCORES = ["r_score", "f_score", "m_score", "l_score"]
LABELS = ["R", "F", "M", "L"]
LOYALTY = {1: "Very high loyalty", 2: "High loyalty", 3: "Medium loyalty", 4: "Low loyalty"}


def _segments(k=4, variables=None):
    """LRFM max-k-cut clusters at k, labelled by Cheng & Chen loyalty rank."""
    variables = variables or config.LRFM_VARS
    df = load_customer_rfml()
    sm = score_matrix(variables)
    rg = reduce_graph(sm)
    super_labels, _, _ = solve_maxkcut(rg, k)
    df = df.copy()
    df["cluster"] = lift_assignment(rg, super_labels).loc[df.index].to_numpy()

    sc = [f"{v.lower()}_score" for v in variables]
    means = df.groupby("cluster")[sc].mean()
    means["distance"] = np.sqrt((means[sc] ** 2).sum(axis=1))   # Cheng & Chen distance from origin
    means["rank"] = means["distance"].rank(ascending=False).astype(int)
    label = {cl: f"{LOYALTY.get(r, f'rank {r}')}" for cl, r in means["rank"].items()}
    df["segment"] = df["cluster"].map(label)

    order = [label[cl] for cl in means.sort_values("rank").index]   # best -> worst
    colors = {seg: PALETTE[i % len(PALETTE)] for i, seg in enumerate(order)}
    return df, order, colors, means


def _summary(df):
    g = df.groupby("segment")
    s = pd.DataFrame({"customers": g.size(), "revenue": g["monetary"].sum()})
    s["pct_customers"] = 100 * s["customers"] / s["customers"].sum()
    s["pct_revenue"] = 100 * s["revenue"] / s["revenue"].sum()
    return s


def fig_value(summ, order):
    y = np.arange(len(order))
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    ax.barh(y - 0.2, summ["pct_customers"].loc[order], 0.4, color="#B8C4D9", label="% of customers")
    ax.barh(y + 0.2, summ["pct_revenue"].loc[order], 0.4, color=PALETTE[0], label="% of revenue")
    for i, seg in enumerate(order):
        ax.text(summ["pct_customers"][seg] + 0.6, i - 0.2, f"{summ['pct_customers'][seg]:.0f}%", va="center", fontsize=9, color="#777")
        ax.text(summ["pct_revenue"][seg] + 0.6, i + 0.2, f"{summ['pct_revenue'][seg]:.0f}%", va="center", fontsize=9, color=PALETTE[0], fontweight="bold")
    ax.set_yticks(y); ax.set_yticklabels(order); ax.invert_yaxis()
    ax.set_xlabel("percent"); ax.set_title("Cluster volume vs value (LRFM, k=4)")
    ax.legend(loc="lower right"); ax.grid(axis="y", visible=False)
    return fig


def fig_heatmap(df, order):
    mat = df.groupby("segment")[SCORES].mean().loc[order]
    mat.columns = LABELS
    fig, ax = plt.subplots(figsize=(6.2, 4.8))
    sns.heatmap(mat, annot=True, fmt=".1f", cmap=SEQ, vmin=1, vmax=5,
                linewidths=1.4, linecolor="white", square=True,
                cbar_kws={"label": "mean score (1=low, 5=high)", "shrink": .8}, ax=ax)
    ax.set_title("Cluster R-F-M-L score profile"); ax.set_ylabel(""); ax.set_xlabel("")
    plt.setp(ax.get_yticklabels(), rotation=0)
    return fig


def fig_boxplot(df, order, colors):
    fig, ax = plt.subplots(figsize=(10, 5.2))
    sns.boxplot(data=df, x="segment", y="monetary", order=order, hue="segment",
                palette=colors, legend=False, fliersize=1.2, linewidth=1.1, width=.6, ax=ax)
    ax.set_yscale("log")
    ax.set_title("Monetary value distribution by cluster"); ax.set_xlabel("")
    ax.set_ylabel("monetary (£, log scale)")
    plt.setp(ax.get_xticklabels(), rotation=12)
    ax.grid(axis="x", visible=False)
    return fig


def fig_profile_bars(df, order):
    """Grouped bars of mean R/F/M/L per cluster (clear, exact-value alternative to radar)."""
    means = df.groupby("segment")[SCORES].mean().loc[order]
    means.columns = LABELS
    long = means.reset_index().melt(id_vars="segment", var_name="metric", value_name="score")
    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    sns.barplot(data=long, x="segment", y="score", hue="metric",
                palette=PALETTE[:4], order=order, ax=ax)
    ax.set_ylim(0, 5); ax.set_xlabel(""); ax.set_ylabel("mean score (1-5)")
    ax.set_title("Cluster R/F/M/L score profiles")
    plt.setp(ax.get_xticklabels(), rotation=12)
    ax.legend(title="", ncol=4, loc="upper right"); ax.grid(axis="x", visible=False)
    return fig


def fig_scatter_2d(df, order, colors):
    """R x M and F x M coloured by cluster - matches the baseline paper's Fig 6."""
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.4))
    for seg in order:
        m = (df.segment == seg).to_numpy()
        ax[0].scatter(df.loc[m, "recency"], df.loc[m, "monetary"], s=7, alpha=.3,
                      color=colors[seg], label=seg, edgecolors="none")
        ax[1].scatter(df.loc[m, "frequency"], df.loc[m, "monetary"], s=7, alpha=.3,
                      color=colors[seg], edgecolors="none")
    ax[0].set_xlabel("recency (days)"); ax[0].set_title("Recency × Monetary")
    ax[1].set_xlabel("frequency (orders)"); ax[1].set_title("Frequency × Monetary"); ax[1].set_xscale("log")
    for a in ax:
        a.set_ylabel("monetary (£, log)"); a.set_yscale("log")
    ax[0].legend(markerscale=2.6, fontsize=9, loc="upper right")
    fig.suptitle("Customer clusters in 2D RFM space", fontweight="bold")
    fig.tight_layout()
    return fig


def fig_rfm_3d(df, order, colors, angles=((20, -60), (20, 30), (35, -120), (15, 150))):
    """Exploratory 3D view of the clusters in R-F-M score space, from 4 angles.

    (Not a paper figure - the paper uses the clearer 2D scatters; this is to
    'see' the cluster structure. Colour = LRFM k=4 loyalty cluster; L is the 4th
    dimension, encoded by colour rather than an axis.)
    """
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    rng = np.random.default_rng(0)
    jit = {c: df[c].to_numpy() + rng.uniform(-.32, .32, len(df))
           for c in ("r_score", "f_score", "m_score")}
    fig = plt.figure(figsize=(11, 9))
    for i, (el, az) in enumerate(angles, 1):
        ax = fig.add_subplot(2, 2, i, projection="3d")
        for seg in order:
            m = (df.segment == seg).to_numpy()
            ax.scatter(jit["r_score"][m], jit["f_score"][m], jit["m_score"][m],
                       s=5, alpha=.35, color=colors[seg], label=seg, edgecolors="none")
        ax.set_xlabel("R", fontsize=8); ax.set_ylabel("F", fontsize=8); ax.set_zlabel("M", fontsize=8)
        ax.set_xticks([1, 3, 5]); ax.set_yticks([1, 3, 5]); ax.set_zticks([1, 3, 5])
        ax.tick_params(labelsize=7)
        ax.view_init(elev=el, azim=az); ax.set_title(f"elev {el}°, azim {az}°", fontsize=9)
        for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
            axis.pane.set_alpha(0.05)
    h, lab = fig.axes[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=4, markerscale=3, fontsize=9)
    fig.suptitle("LRFM k=4 clusters in 3D R-F-M score space (4 viewing angles)",
                 fontweight="bold")
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    return fig


def explore_3d() -> None:
    """Generate the exploratory 3D figure (separate from the paper set)."""
    set_style()
    df, order, colors, _ = _segments(k=4)
    print("saved:", save(fig_rfm_3d(df, order, colors), "viz_rfm_3d_explore.png"))


def main() -> None:
    set_style()
    df, order, colors, means = _segments(k=4)
    summ = _summary(df)
    print("loyalty ranking (Cheng & Chen distance):")
    print(means.sort_values("rank")[["distance", "rank"]].to_string())

    # remove stale figures from the previous (radar/3d) design
    for old in ("viz_segment_radar.png", "viz_rfm_3d.png"):
        (config.FIGURES / old).unlink(missing_ok=True)

    saved = [
        save(fig_value(summ, order), "viz_segment_value.png"),
        save(fig_heatmap(df, order), "viz_segment_heatmap.png"),
        save(fig_boxplot(df, order, colors), "viz_segment_boxplot.png"),
        save(fig_profile_bars(df, order), "viz_segment_profile_bars.png"),
        save(fig_scatter_2d(df, order, colors), "viz_segment_scatter2d.png"),
    ]
    print("\nsaved modern figures:")
    for p in saved:
        print("  ", p.split("/")[-1])


if __name__ == "__main__":
    main()
