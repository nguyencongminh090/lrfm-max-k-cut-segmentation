"""Stage 2 - Feature Engineering analysis: FE-2, FE-3, FE-5.

FE-1 (raw R/F/M/L) and FE-4 (1..5 scores) already live in SQL (customer_rfml).
This module:
  FE-2  distribution analysis (skew/kurtosis, L=0 mass, Spearman correlations)
  FE-3  LRFM justification: does L add NON-REDUNDANT resolution? (decision gate)
  FE-5  figures (histograms, correlation heatmap, scatters, Pareto)
Writes results/tables/stage2_feature_report.md and results/figures/*.png.

Run:  python -m src.feature_eng
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import skew, kurtosis

from . import config
from .features import load_customer_rfml
from .viz_style import set_style

REPORT = config.TABLES / "stage2_feature_report.md"
RAW = ["recency", "frequency", "monetary", "length"]
SCORES = ["r_score", "f_score", "m_score", "l_score"]
_lines: list[str] = []


def out(s: str = "") -> None:
    print(s)
    _lines.append(s)


# --------------------------------------------------------------------------- #
# FE-2 - distribution analysis
# --------------------------------------------------------------------------- #
def fe2(df: pd.DataFrame) -> None:
    out("# Stage 2 - Feature Engineering report\n")
    out("## FE-2 - Distribution analysis")
    rows = []
    for c in RAW:
        s = df[c].astype(float)
        rows.append([c, s.min(), s.median(), s.mean(), s.max(), skew(s), kurtosis(s)])
    tab = pd.DataFrame(rows, columns=["var", "min", "median", "mean", "max", "skew", "kurt"])
    out(tab.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    zero_len = (df["length"] == 0).mean()
    out(f"\n- one-time buyers (length==0): {(df['length']==0).sum():,} "
        f"({100*zero_len:.1f}%)  -> the L-score tie mass (FE-4.2)")

    out("\n- Spearman correlation (raw R,F,M,L):")
    out(df[RAW].corr(method="spearman").to_string(float_format=lambda x: f"{x:,.2f}"))
    out("\n- Spearman correlation (scores r,f,m,l):")
    out(df[SCORES].corr(method="spearman").to_string(float_format=lambda x: f"{x:,.2f}"))
    out("\n- Note: scoring is quantile/rank-based -> robust to the heavy skew above; "
        "no scaling/log needed before clustering.\n")


# --------------------------------------------------------------------------- #
# FE-3 - LRFM justification (decision gate)
# --------------------------------------------------------------------------- #
def fe3(df: pd.DataFrame) -> None:
    out("## FE-3 - LRFM justification (does L earn its place?)")

    # (1) redundancy: L vs R,F,M -- judged RELATIVE to RFM's own internal
    #     redundancy (F-M is already ~0.81), not an arbitrary absolute cutoff.
    sc = df[SCORES].corr(method="spearman")
    corr = sc["l_score"].drop("l_score")
    out("- (1) Redundancy check - Spearman(L_score, .):")
    out(corr.to_string(float_format=lambda x: f"{x:,.2f}"))
    l_max = corr.abs().max()
    rfm = sc.loc[["r_score", "f_score", "m_score"], ["r_score", "f_score", "m_score"]]
    rfm_internal_max = rfm.where(~np.eye(3, dtype=bool)).abs().max().max()
    out(f"     L's max |corr| with R/F/M  = {l_max:.2f}")
    out(f"     RFM's OWN internal max |corr| = {rfm_internal_max:.2f} (already accepted, e.g. F-M)")
    out(f"     -> L is {'NO more redundant than M already is within RFM' if l_max <= rfm_internal_max + 0.1 else 'notably more redundant than the RFM axes'}")

    # (2) resolution gain: how much finer does L make the segmentation?
    rfm_cells = df.groupby(["r_score", "f_score", "m_score"]).ngroups
    lrfm_cells = df.groupby(["l_score", "r_score", "f_score", "m_score"]).ngroups
    out(f"\n- (2) Resolution gain:")
    out(f"     distinct (R,F,M) cells   = {rfm_cells}")
    out(f"     distinct (L,R,F,M) cells = {lrfm_cells}")
    out(f"     granularity multiplier   = {lrfm_cells/rfm_cells:.2f}x "
        f"(L splits the RFM space {lrfm_cells/rfm_cells:.2f}-fold)")

    # (3) within-RFM-cell separation by L
    by = df.groupby(["r_score", "f_score", "m_score"])
    ndistinct_L = by["l_score"].nunique()
    split = ndistinct_L > 1
    cust_in_split = df.set_index(["r_score", "f_score", "m_score"]).index.map(
        ndistinct_L.to_dict()).to_series().gt(1).mean()
    out(f"\n- (3) Within-(R,F,M)-cell separation by L:")
    out(f"     {split.sum()}/{len(split)} RFM cells contain >1 distinct L-score "
        f"({100*split.mean():.0f}% of cells)")
    out(f"     {100*cust_in_split:.0f}% of customers live in an RFM cell that L sub-divides")

    # (4) concrete example: a populous RFM cell that L pulls apart
    biggest = by.size().sort_values(ascending=False)
    for cell in biggest.index:
        sub = df[(df.r_score == cell[0]) & (df.f_score == cell[1]) & (df.m_score == cell[2])]
        if sub["l_score"].nunique() >= 2:
            out(f"\n- (4) Example RFM cell (R,F,M)={tuple(int(c) for c in cell)} has {len(sub)} customers "
                f"spanning L-scores {sorted(int(x) for x in sub['l_score'].unique())}:")
            ex = (sub.sort_values("length")
                     .groupby("l_score")
                     .agg(n=("length", "size"),
                          length_min=("length", "min"),
                          length_mean=("length", "mean"),
                          length_max=("length", "max")))
            out(ex.to_string(float_format=lambda x: f"{x:,.0f}"))
            out("     -> same R/F/M, but L separates short-tenure (new) from "
                "long-tenure (loyal) customers.")
            break

    verdict = (lrfm_cells / rfm_cells > 1.5) and (l_max <= rfm_internal_max + 0.1)
    if verdict:
        out(f"\n- VERDICT: GO - L adds {lrfm_cells/rfm_cells:.1f}x resolution and is no more "
            f"redundant than M already is within RFM; keep LRFM. (Confirm the payoff "
            f"empirically via the segmentation comparison.)\n")
    else:
        out(f"\n- VERDICT: CAUTION - L's redundancy ({l_max:.2f}) exceeds RFM's internal "
            f"({rfm_internal_max:.2f}) by >0.1; keep but flag, let modeling decide.\n")


# --------------------------------------------------------------------------- #
# FE-5 - figures
# --------------------------------------------------------------------------- #
def fe5(df: pd.DataFrame) -> None:
    out("## FE-5 - Figures (saved to results/figures/)")
    config.FIGURES.mkdir(parents=True, exist_ok=True)

    # histograms (log1p for the long-tailed F, M)
    fig, ax = plt.subplots(2, 2, figsize=(10, 7))
    for a, c in zip(ax.ravel(), RAW):
        vals = df[c].astype(float)
        a.hist(np.log1p(vals) if c in ("frequency", "monetary") else vals, bins=50)
        a.set_title(f"{c}{' (log1p)' if c in ('frequency','monetary') else ''}")
    fig.tight_layout(); fig.savefig(config.FIGURES / "fe5_histograms.png", dpi=110); plt.close(fig)

    # Spearman correlation heatmap (clean lower-triangle, soft diverging map)
    corr = df[RAW].corr(method="spearman")
    corr.index = corr.columns = ["Recency", "Frequency", "Monetary", "Length"]
    mask = np.triu(np.ones_like(corr, dtype=bool))          # hide upper triangle + diagonal
    fig, a = plt.subplots(figsize=(5.8, 4.8))
    sns.heatmap(corr, mask=mask, annot=True, fmt=".2f", cmap="vlag",
                vmin=-1, vmax=1, center=0, square=True,
                linewidths=1.6, linecolor="white",
                cbar_kws={"label": "Spearman ρ", "shrink": .75},
                annot_kws={"fontsize": 9.5}, ax=a)
    a.set_title("Spearman correlation  (R, F, M, L)")
    plt.setp(a.get_yticklabels(), rotation=0)
    plt.setp(a.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout(); fig.savefig(config.FIGURES / "fe5_corr_heatmap.png"); plt.close(fig)

    # scatters vs monetary
    fig, ax = plt.subplots(1, 3, figsize=(15, 5))
    for a, c in zip(ax, ["recency", "frequency", "length"]):
        a.scatter(df[c], df["monetary"], s=6, alpha=.25)
        a.set_xlabel(c); a.set_ylabel("monetary (log)"); a.set_yscale("log")
    fig.suptitle("Monetary vs Recency / Frequency / Length", fontweight="bold")
    fig.tight_layout()
    fig.savefig(config.FIGURES / "fe5_scatter_vs_monetary.png", dpi=110); plt.close(fig)

    # Pareto: cumulative revenue vs customer rank
    m = df["monetary"].sort_values(ascending=False).to_numpy()
    cum = np.cumsum(m) / m.sum()
    fig, a = plt.subplots(figsize=(6, 4))
    a.plot(np.arange(1, len(cum) + 1) / len(cum) * 100, cum * 100)
    a.axhline(80, ls="--", c="grey"); a.axvline(20, ls="--", c="grey")
    a.set_xlabel("% of customers (richest first)"); a.set_ylabel("% of revenue")
    a.set_title("Pareto: revenue concentration")
    fig.tight_layout(); fig.savefig(config.FIGURES / "fe5_pareto.png", dpi=110); plt.close(fig)

    top20 = cum[int(0.2 * len(cum))] * 100
    out(f"- saved 4 figures. Pareto: top 20% of customers = {top20:.1f}% of revenue.")
    out("  files: fe5_histograms.png, fe5_corr_heatmap.png, fe5_scatter_vs_monetary.png, fe5_pareto.png\n")


def main() -> None:
    set_style()
    df = load_customer_rfml()
    fe2(df)
    fe3(df)
    fe5(df)
    config.TABLES.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(_lines))
    print(f"\n>>> report written to {REPORT}")


if __name__ == "__main__":
    main()
