# Development Workflow — LRFM + max-k-cut

Goal: reproduce the RFM/max-k-cut baseline, then show the **LRFM** extension
yields richer, more actionable segments. Frame the win on **segment quality /
business actionability**, not raw silhouette (silhouette tends to dip as
dimensionality grows from 3 → 4).

## Phases

### Phase 0 — Environment ✅ scaffolded
- [ ] Create venv & install `requirements.txt`. **Risk:** system Python is 3.14;
      `gurobipy` / wheels may lag. Prefer a **Python 3.11 or 3.12** venv (paper
      used 3.12.2) to guarantee wheels exist.
- [ ] Activate Gurobi free academic license (`grbgetkey`). If unavailable, use
      the open-source fallback (see "Solver fallback" below).

### Phase 1 — Data & RFM baseline reproduction
- [ ] Download Online Retail II `.xlsx` → `data/raw/`.
- [ ] `src/data_loader.py`: confirm sheet names; verify cleaning hits
      **~79,104 transactions / 5,878 customers** (paper's numbers = correctness check).
- [ ] `src/rfm.py`: confirm Table-1 stats (Recency mean ≈ 200.87, Frequency mean
      ≈ 6.30, Monetary mean ≈ 2,965.56) before scoring.
- [ ] **Validation gate:** reduced RFM graph must have ~**114 super-vertices**
      (paper) and the k=2..10 silhouette curve must match Table 6
      (k=2 ≈ 0.46, k=4 ≈ 0.40). If it doesn't, the reproduction is wrong — stop
      and debug before touching LRFM.

### Phase 2 — LRFM extension
- [ ] Add `L` (already wired in `config.LRFM_VARS`). Inspect L distribution;
      decide whether tenure is informative on this 2-year window.
- [ ] Run `--mode extended`; confirm reduced graph ≤ 625 super-vertices.
- [ ] Sweep k=2..10; record silhouette + objective + solver gap/time.

### Phase 3 — Comparison & analysis
- [ ] Side-by-side silhouette table (RFM vs LRFM) — reproduce paper's Fig-5 style.
- [ ] Business profiling (`evaluate.profile_clusters`, `loyalty_ranking`):
      show LRFM separates segments RFM cannot (e.g. *new* vs *long-tenure-loyal*
      low-recency buyers). **This is the core argument.**
- [ ] Figures: silhouette-vs-k, R×M / F×M scatter per cluster, monthly trends.

### Phase 4 — Write-up
- [ ] Methods, reproduction fidelity, LRFM results, business interpretation,
      honest discussion of the silhouette trade-off.

## Decision points (need your call)
1. **Solver:** Gurobi academic (faithful) vs open-source fallback? Default: Gurobi.
2. **k selection:** silhouette-best vs business-best (paper chose k=4 over k=2 for
   business value). Default: report both, recommend on business value.
3. **Silhouette metric:** euclidean (sklearn default) vs manhattan (matches the
   edge weight). Default: euclidean; report manhattan as robustness check.
4. **L definition:** first→last purchase span (tenure). Alternative: days since
   first purchase (observation length). Default: first→last span.

## Solver fallback (no Gurobi)
The BQO objective `w_ij(1 - Σ_l x_il x_jl)` is quadratic. To use CBC/PuLP,
linearize same-cluster products `y_ijl = x_il·x_jl` with the standard 3
constraints (`y ≤ x_il`, `y ≤ x_jl`, `y ≥ x_il+x_jl-1`). Tractable on the
reduced graph (≤625 vertices). Implement in `maxkcut.py` only if needed.

## Reproduction targets (correctness anchors)
| Quantity | Paper value |
|---|---|
| Clean transactions | 79,104 |
| Customers | 5,878 |
| Reduced RFM super-vertices | 114 |
| Silhouette k=2 (max-k-cut) | 0.4569 |
| Silhouette k=4 (max-k-cut) | 0.3980 |
| Best k (silhouette / business) | 2 / 4 |
