# Stage 2 — Feature Engineering (LRFM)

**Scope.** From the **cleaned transaction table** (output of Stage 1, Phases A–E) →
**model-ready customer features**: raw R/F/M/L, their distribution treatment, the
LRFM-justification evidence, the 1..T scores, supporting figures, and cached
artifacts.
**This is a design** — no code. Broken into small sub-stages (FE-1 … FE-6) so each
can be approved/tracked independently.

**Input:** `data/processed/transactions_clean.parquet` (5,878 customers).
**Reconciliation anchors (graph paper):** Recency mean ≈ **200.87**, Frequency mean
≈ **6.30**, Monetary mean ≈ **2,965.56**.

---

## FE-1 — Customer-level aggregation (raw R, F, M, L)
*Build one row per customer.*
- **FE-1.1.** Snapshot date = max `InvoiceDate` in the cleaned data.
- **FE-1.2.** **R** = days from customer's last purchase to snapshot.
- **FE-1.3.** **F** = number of unique invoices (= "transactions").
- **FE-1.4.** **M** = Σ(Quantity × Price) over the customer.
- **FE-1.5.** **L** = days between customer's first and last purchase (tenure).
- **FE-1.6.** Reconcile R/F/M means vs the paper (200.87 / 6.30 / 2,965.56) —
  correctness gate before going further.
*Output:* raw per-customer R,F,M,L table.

## FE-2 — Distribution analysis & transformation decisions
*Understand the feature distributions (revisits skew at the customer level).*
- **FE-2.1.** Skewness/kurtosis of R, F, M, L; confirm heavy right tails in F, M.
- **FE-2.2.** Zero/degenerate mass: **one-time buyers (F=1 ⇒ L=0)** — quantify the
  share (drives the binning decision in FE-4).
- **FE-2.3.** Decide transformation policy: since scoring uses **quantiles** (rank-
  based), raw scale/skew won't affect scores — but log views are kept for plots.
- **FE-2.4.** **Spearman correlations** among R, F, M, L (expect F–M strong).
*Output:* distribution report + transformation/binning decisions.

## FE-3 — LRFM justification (does L earn its place?) *(core of the contribution)*
- **FE-3.1.** Redundancy check: is L explained by F or M? (correlation + conditional
  spread). L must carry **non-redundant** information.
- **FE-3.2.** Separation evidence: among customers with (near-)identical (R,F,M),
  show L splits them — e.g. *new* low-recency vs *long-tenure loyal* low-recency.
  Concrete cross-tabs / example customers.
- **FE-3.3.** Verdict: keep L as a 4th axis (go) or reconsider (no-go) — recorded
  **before** modeling so the decision is principled.
*Output:* the "why LRFM" evidence the write-up rests on.

## FE-4 — Scoring / binning into 1..T
- **FE-4.1.** Quantile-bin each of R, F, M, L into integer scores **1..T (T=5)**,
  **1 = worst, T = best**; invert R (fewer days = better).
- **FE-4.2.** Handle the **L=0 tie mass** (one-time buyers) so quantile edges don't
  collapse — decide bin strategy (e.g. rank-based with ties → lowest bin).
- **FE-4.3.** Validate bin balance (each score ~ equal count where ties allow);
  produce the (R,F,M,L)-score per customer.
- **FE-4.4.** Sanity: distinct (R,F,M)-score cells ≤ 125, (R,F,M,L) ≤ 625
  (the reduced-graph bound the solver relies on).
*Output:* `customers_rfml.parquet` with raw + scored columns (model-ready).

## FE-5 — Visualization
- **FE-5.1.** Histograms of R, F, M, L (raw + log).
- **FE-5.2.** Box/violin plots (outlier visibility).
- **FE-5.3.** **Spearman correlation heatmap** (R, F, M, L).
- **FE-5.4.** Monthly revenue & order-count time series (seasonality/holiday spike).
- **FE-5.5.** Scatter **R×M**, **F×M** (reproduce paper) + **L×M**, **L×R** (ours).
- **FE-5.6.** Pareto curve (cumulative revenue vs customer rank).
*Output:* figures in `results/figures/`.

## FE-6 — Artifacts & hand-off to modeling
- **FE-6.1.** Persist `customers_rfml.parquet` (raw + scores).
- **FE-6.2.** Feature dictionary (definition + unit + range for each feature).
- **FE-6.3.** Reconciliation table vs papers (counts + R/F/M means).
- **FE-6.4.** Confirm score matrix is ready for the graph/max-k-cut stage
  (RFM baseline vs LRFM extension).
*Output:* model-ready dataset + docs. **→ hand off to modeling (max-k-cut).**

---

### Dependencies / ordering
FE-1 → FE-2 → FE-3 (gate: L justified?) → FE-4 → FE-5 → FE-6.
FE-3 is a **decision gate**: if L proves redundant, revisit before scoring.

### Watch-outs
- **L=0** for one-time buyers → big tie cluster; affects quantile bins (FE-4.2).
- Keep Frequency = **#invoices** consistent with Stage-1 decision E7.
- Scores are quantile/rank-based → robust to skew & outliers (no scaling needed).
- Don't let non-product StockCodes (if kept) silently distort M (trace back to E5).
