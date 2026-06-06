"""Modern, presentation/paper-grade plotting style (shared by all figures).

Design choices: no top/right spines, soft light gridlines, generous padding,
bold concise titles, a curated muted categorical palette, and a perceptually
uniform sequential colormap. Larger fonts ("talk" context) so figures read well
on slides. Call `set_style()` once, build the figure, then `save(fig, name)`.
"""
from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns

from . import config

# curated modern categorical palette (muted, colour-blind friendly-ish)
PALETTE = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3",
           "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD"]
SEQ = "mako"          # sequential colormap for heatmaps
INK = "#2B2B2B"       # primary text/edge colour
MUTED = "#8A8A8A"     # secondary/reference colour


def set_style() -> None:
    sns.set_theme(style="whitegrid", context="notebook")
    mpl.rcParams.update({
        "figure.facecolor": "white", "savefig.facecolor": "white",
        "figure.dpi": 120, "savefig.dpi": 200, "savefig.bbox": "tight",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": INK, "axes.linewidth": 0.8,
        "axes.titlesize": 11.5, "axes.titleweight": "bold", "axes.titlepad": 8,
        "axes.titlecolor": INK,
        "axes.labelsize": 9.5, "axes.labelcolor": INK,
        "text.color": INK, "xtick.color": INK, "ytick.color": INK,
        "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
        "grid.color": "#E6E6E6", "grid.linewidth": 0.7,
        "legend.frameon": False, "legend.fontsize": 8.5, "legend.title_fontsize": 9,
        "figure.titlesize": 12.5, "figure.titleweight": "bold",
        "font.size": 9.5, "font.family": "sans-serif",
        "axes.prop_cycle": mpl.cycler(color=PALETTE),
    })


def save(fig, name: str) -> str:
    config.FIGURES.mkdir(parents=True, exist_ok=True)
    path = config.FIGURES / name
    fig.savefig(path)
    plt.close(fig)
    return str(path)
