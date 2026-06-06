# LRFM Max-k-cut Customer Segmentation

Reproducing and extending the graph-based, **maximum k-cut** RFM customer-segmentation
method of Corrêa Vianna Filho, de Lima & Kleina (2026) on the public **Online Retail II**
dataset — and extending it with a **Length / tenure** dimension (**RFM → LRFM**).

> **Course:** DAP391m · **Authors:** Cong Minh Nguyen, Duc Nhat Vo, Nguyen Minh Hai Tran ·
> **Supervisor:** Hoang Linh Nguyen · FPT University.

## What this project does

- **Reproduces the baseline** (graph-theory max-k-cut on RFM scores). The baseline released
  **no code**, so the solver is re-implemented from the paper's reduction procedures and BQO
  formulation. Reproduction is exact on the key anchors (5,878 customers, recency mean 200.87,
  114-vertex reduced graph, silhouette within 0.02 of the published values).
- **Extends RFM → LRFM** by adding **L = tenure** (days between a customer's first and last
  purchase), preserving the vertex-reduction guarantee (≤ T⁴ = 625 super-vertices; 313 in our data).
- **Implements a licence-free max-k-cut solver** — multi-start local search + Kernighan–Lin,
  JIT-compiled with Numba — validated against brute-force optima (40/40). No Gurobi/commercial
  solver required.
- **Honest finding:** LRFM does *not* raise the silhouette index (it falls, as expected for a
  4th dimension); its value is **managerial actionability** — it separates newly-acquired from
  long-tenured loyal customers, which RFM cannot. On identical features, K-means is comparable
  to max-k-cut.

## Repository layout

```
src/
  config.py         parameters (T=5, RFM/LRFM variable sets, k range, paths, solver)
  eda.py            Stage 1 — EDA + cleaning  -> transactions_clean.parquet, stage1_report.md
  build_db.py       SQLite 3NF schema + R/F/M/L quantile scores (SQL = source of truth)
  features.py       read customer_rfml from SQL; named-segment helper
  feature_eng.py    Stage 2 — distribution analysis, LRFM justification, figures
  graph.py          customer graph: reduction (Procedure 1) + lift-back (Procedure 2)
  maxkcut.py        licence-free max-k-cut solver (Numba local search + Kernighan–Lin)
  evaluate.py       silhouette, cluster profiling, Cheng–Chen loyalty ranking
  pipeline.py       end-to-end experiment for one variable set
  modeling.py       Stage 3 — RFM baseline vs LRFM
  compare.py        all methods (max-k-cut / K-means / Ward / GMM) vs the paper
  sql_analysis.py   "Data Analysis with SQL" deliverable -> sql/analysis.sql
  viz.py            modern segment figures   viz_style.py  shared figure theme
  proposal.py / audit_log.py   generate the proposal .docx and AI Audit Log .xlsx
tests/validate_solver.py   solver correctness (brute force) + speed + robustness
docs/             EDA_PLAN.md, FEATURE_ENGINEERING_PLAN.md, DB_SCHEMA.md
results/
  tables/*.md      stage reports         figures/*.png   all figures
  paper/           Springer LaTeX paper (main.tex, refs.bib, build.sh) -> main.pdf
  AI_Audit_Log_DAP391m.xlsx · Research_Proposal_DAP391m.docx
papers/           the two reference papers (txt + pdf)
WORKFLOW.md       development plan, decisions, reproduction anchors
```

## Setup

The scientific stack lacks wheels for Python 3.14, so use **Python 3.13**:

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt     # pinned versions in requirements.lock
```

Download the dataset to `data/raw/online_retail_II.xlsx`
(UCI Online Retail II, dataset 502: https://archive.ics.uci.edu/dataset/502/online+retail+ii).

> No Gurobi licence is needed — the default solver is the from-scratch Numba+KL heuristic
> (`config.SOLVER = "local"`). `gurobipy`/`pulp` backends are optional alternatives.

## Reproduce the full pipeline

```bash
python -m src.eda            # 1. clean data            -> data/processed/transactions_clean.parquet
python -m src.build_db       # 2. 3NF SQLite + scores   -> data/processed/retail.db
python -m src.feature_eng    # 3. distribution + LRFM justification (FE-2/3/5)
python -m src.modeling       # 4. RFM baseline vs LRFM  -> results/tables/stage3_modeling_report.md
python -m src.compare        # 5. method comparison vs paper
python -m src.sql_analysis   # 6. SQL analysis deliverable -> sql/analysis.sql
python -m src.viz            # 7. modern segment figures
python -m tests.validate_solver   # solver correctness / speed / robustness
```

Stages 4–7 read scores from `retail.db`, so run `build_db` first. `run.py --mode both` is a
shortcut that runs the RFM-vs-LRFM experiment via `pipeline.py`.

## Method (one paragraph)

Each customer is scored 1–5 on R, F, M (and L) by quantiles, becoming a vertex of a graph whose
edge weights are Manhattan distances between score vectors. Customers with identical scores merge
into super-vertices (≤ T^q), so the reduced graph is tiny (114 for RFM, 313 for LRFM) regardless of
customer count; clustering it is equivalent to clustering the full data. Segmentation into k groups
is the maximum k-cut problem, solved on the reduced graph by the licence-free heuristic. Clusters
are evaluated by silhouette and ranked by Cheng–Chen loyalty distance (Very high → Low loyalty).

## Deliverables

- **Paper** — `results/paper/` (Springer `sn-jnl`). Compile: `cd results/paper && ./build.sh` → `main.pdf`
  (needs a TeX Live install). Reviewed by content/template/reference sub-agents.
- **Research proposal** — `results/Research_Proposal_DAP391m.docx` (`python -m src.proposal`).
- **AI Audit Log** — `results/AI_Audit_Log_DAP391m.xlsx` (`python -m src.audit_log`; appendable).

## Key references

- Corrêa Vianna Filho, de Lima & Kleina (2026), *RFM model customer segmentation from a graph
  theory perspective*, Quality & Quantity — the **baseline**.
- Rungruang et al. (2024), *RFM model customer segmentation based on hierarchical approach using
  FCA*, Expert Systems with Applications — the FCA comparator.
- Cheng & Chen (2009), customer-value/loyalty RFM ranking. Rousseeuw (1987), silhouette index.

Full, DOI-verified bibliography in `results/paper/refs.bib`.

## Data & code availability

The dataset is public (UCI). All analysis code is in `src/`; the modeling pipeline runs entirely
on open-source tools (pandas, scikit-learn, NumPy, Numba, SQLite). See `WORKFLOW.md` for design
decisions and the reproduction anchors.
