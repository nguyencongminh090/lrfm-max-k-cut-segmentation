# Stage 1 — EDA & Data Cleaning (Phases A–E)

**Scope.** From raw `online_retail_II.xlsx` → a **cleaned, attributed transaction
table**. Ends at "data cleaned". Customer-level features (R/F/M/L), scoring, and
visualization belong to **Stage 2 — Feature Engineering** (see
`FEATURE_ENGINEERING_PLAN.md`).
**This is a design** — analysis steps, what each inspects, the decision it drives.
No code.

**Added per request:** distribution diagnostics — **skew, imbalance, concentration,
zero-inflation** — are checked throughout A–E (on transaction-level fields; the
customer-level R/F/M/L skew is revisited in Stage 2).

**Raw facts (verified).** 2 sheets (`Year 2009-2010`, `Year 2010-2011`), 8 cols:
`Invoice, StockCode, Description, Quantity, InvoiceDate, Price, Customer ID,
Country`. Expected ~1,067,371 rows.

**Reconciliation anchors.**
| Quantity | FCA (2024) | Graph (2026) |
|---|---|---|
| Raw records | 1,067,371 | 1,067,371 |
| After cleaning | 805,549 *(line items)* | 79,104 *("transactions")* |
| Customers | 5,878 | 5,878 |
> ⚠️ ~10× gap = **unit mismatch**: 805,549 = surviving *line items*; 79,104 ≈ *unique
> invoices*. Both reach **5,878 customers** — our real anchor. Phase E must pin the unit.

---

## Phase A — Ingestion & structural overview
*Small steps:*
- **A1.** Load both sheets; **tag each row with its source sheet/year**.
- **A2.** Concatenate; record total rows, dtypes, memory, head/tail.
- **A3.** Check **cross-sheet overlap** for shared 2010 months (double-count risk).
- **A4.** Normalize headers (`Customer ID`→`CustomerID`); parse `InvoiceDate` to
  datetime; confirm `CustomerID` is integer-like (stored as float `.0`).
- **A5.** Sanity: raw row count == 1,067,371.
*Output:* a single typed raw frame + structural notes.

## Phase B — Univariate profiling **+ distribution shape**
For every column: missing %, n-unique, value distribution, format quirks **and
distribution shape**.
- **B1. Invoice** — 6-digit; **`C` prefix = cancellation**; scan other letter
  prefixes (`A` = adjustment). Count cancellations + their share.
- **B2. StockCode** — flag **non-product codes** (`POST, DOT, M, C2, BANK CHARGES,
  AMAZONFEE, S, D, gift_0001…, TEST, ADJUST`); **frequency distribution = long tail?**
- **B3. Description** — missing rows; junk markers (`?`, `damaged`, `lost`, `check`).
- **B4. Quantity** — **skewness & kurtosis**, zero/negative counts, extreme highs.
- **B5. Price (unit)** — **skewness**, zeros, negatives (`Adjust bad debt`), extremes.
- **B6. InvoiceDate** — min/max (expect 2009-12-01→2011-12-09), **rows-per-month
  balance** (is the 2-yr panel temporally balanced? seasonal spikes?).
- **B7. CustomerID** — **missing rate** (large unattributed block), n-unique.
- **B8. Country** — **imbalance** (expect UK ~90%+; quantify with share +
  Herfindahl/Gini); `Unspecified`, `EIRE`, `European Community`.
*Output:* per-column profile table incl. skew/kurtosis for numerics.

## Phase C — Missingness & duplicates
- **C1.** Missing-value matrix; size + characterize the **missing-CustomerID block**
  (does it correlate with country/date?).
- **C2.** **Exact duplicate rows** count.
- **C3.** **Partial duplicates** (Invoice+StockCode+Quantity+Price) — real or artifact?
*Output:* counts + rationale for each removable group.

## Phase D — Anomalies **+ imbalance / concentration diagnostics**
- **D1. Cancellations / returns:** `C`-invoices & negative quantities; attempt to
  match cancellations to original sales (note: not always 1:1).
- **D2. Zero/negative Price or Quantity** — tabulate before dropping.
- **D3. Non-merchandise StockCodes** — their **share of revenue**.
- **D4. Outliers** in Quantity/Price/line-revenue — **describe, do NOT remove**
  (graph-paper policy; contrast FCA's IQR path).
- **D5. Concentration / imbalance (key new block):**
  - **Revenue concentration** by customer (**Pareto curve + Gini**) — validate "80/20".
  - **Revenue concentration** by product (top-N StockCode share).
  - **Geographic imbalance** (UK vs rest).
  - **Cancellation ratio** (#C-invoices / total), **missing-ID share**.
  - **Purchase-count distribution** across customers (#invoices per customer) —
    expect heavy right-skew & a large **one-time-buyer** mass (previews the L=0
    issue in Stage 2).
*Output:* a distribution/imbalance summary (skew, Gini, dominance ratios).

## Phase E — Cleaning decision log *(the Stage-1 deliverable)*
Explicit, ordered, justified, reconciled rules:
1. Drop missing `CustomerID`.
2. Drop `Quantity <= 0`.
3. Drop `Price <= 0`.
4. Drop exact duplicate rows.
5. **Decide** keep/drop non-product StockCodes (default keep; record revenue impact).
6. **Keep outliers** (no IQR/clip) — match the graph-paper baseline.
7. Define **"transaction" = unique Invoice**; flag that **Frequency = #invoices**.
8. **Reconcile:** surviving line items, surviving invoices, **customers == 5,878**.
*Output:* `data/processed/transactions_clean.parquet` + decision log + reconciliation
table. **→ hand off to Stage 2 (Feature Engineering).**

---

### Distribution-diagnostics checklist (collected, for A–E)
- **Skew/kurtosis:** Quantity, Price, line-revenue (expect strong right-skew).
- **Zero-inflation:** % zero/neg in Quantity & Price.
- **Imbalance:** Country dominance (UK%), cancellation ratio, missing-ID share.
- **Concentration:** revenue Gini by customer & by product; Pareto check.
- **Temporal balance:** transactions per month across the 2-year window.
- **Purchase-count skew:** invoices-per-customer (one-time-buyer mass).

### Watch-outs
- Unit confusion: line items vs invoices (805,549 / 79,104).
- Cross-sheet 2010 overlap (double-count).
- `Customer ID` has a space; stored as float `.0`.
- Cancellation `C`-invoice may have no matching positive row.
- Don't IQR-trim — extremes are wanted for this baseline.
