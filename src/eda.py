"""Stage 1 - EDA & Data Cleaning (Phases A-E) for Online Retail II.

Runs the design in docs/EDA_PLAN.md: structural overview, univariate profiling
with distribution shape (skew/kurtosis), missingness/duplicates, anomaly +
imbalance/concentration diagnostics, then the ordered cleaning decision log.
Prints a report, saves it to results/tables/stage1_report.md, and writes the
cleaned transactions to data/processed/transactions_clean.parquet.

Run:  python -m src.eda
"""
from __future__ import annotations

import re
import numpy as np
import pandas as pd
from scipy.stats import skew, kurtosis

from . import config

REPORT = config.TABLES / "stage1_report.md"
RAW_CACHE = config.DATA_PROCESSED / "transactions_raw.parquet"
CLEAN_OUT = config.DATA_PROCESSED / "transactions_clean.parquet"

_lines: list[str] = []


def out(s: str = "") -> None:
    print(s)
    _lines.append(s)


def gini(x: np.ndarray) -> float:
    """Gini concentration of a non-negative vector (0 = equal, 1 = concentrated)."""
    x = np.sort(np.asarray(x, float))
    x = x[x >= 0]
    if x.sum() == 0:
        return float("nan")
    n = len(x)
    cum = np.cumsum(x)
    return float((n + 1 - 2 * (cum.sum() / cum[-1])) / n)


# --------------------------------------------------------------------------- #
# Phase A - Ingestion & structural overview
# --------------------------------------------------------------------------- #
def phase_a() -> pd.DataFrame:
    out("# Stage 1 - EDA & Data Cleaning report\n")
    out("## Phase A - Ingestion & structural overview")
    fresh = not RAW_CACHE.exists()
    if fresh:
        sheets = pd.read_excel(config.RAW_RETAIL_FILE, sheet_name=None)
        for name, s in sheets.items():
            s["SourceSheet"] = name
        # A3: cross-sheet invoice overlap
        names = list(sheets)
        inv = [set(sheets[n]["Invoice"].astype(str)) for n in names]
        overlap = inv[0] & inv[1]
        out(f"- sheets: {names}")
        out(f"- rows per sheet: {[len(sheets[n]) for n in names]}")
        out(f"- A3 cross-sheet shared Invoice ids: {len(overlap):,}")
        df = pd.concat(sheets.values(), ignore_index=True)
    else:
        df = pd.read_parquet(RAW_CACHE)
        out(f"- loaded cached raw parquet ({len(df):,} rows)")

    # A4: normalize headers + types (must precede caching). Several text columns
    # are mixed int/str object dtype (e.g. Invoice 'C489449', numeric Descriptions);
    # cast every text column to pandas nullable 'string' -> preserves <NA> for the
    # missingness analysis AND is parquet-writable.
    df.columns = [c.strip().replace(" ", "") for c in df.columns]
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    for c in df.select_dtypes("object").columns:
        df[c] = df[c].astype("string")
    if fresh:
        config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
        df.to_parquet(RAW_CACHE)
    out(f"- total raw rows: {len(df):,}  (expected 1,067,371)")
    out(f"- columns: {list(df.columns)}")
    out(f"- dtypes:\n{df.dtypes.to_string()}")
    out(f"- date range: {df['InvoiceDate'].min()} -> {df['InvoiceDate'].max()}")
    out("")
    return df


# --------------------------------------------------------------------------- #
# Phase B - Univariate profiling + distribution shape
# --------------------------------------------------------------------------- #
NONPRODUCT = re.compile(r"^\d{5}[A-Za-z]?$")  # normal product codes match this


def dist_shape(s: pd.Series) -> str:
    s = s.dropna().astype(float)
    return (f"min={s.min():,.2f} med={s.median():,.2f} mean={s.mean():,.2f} "
            f"max={s.max():,.2f} skew={skew(s):,.2f} kurt={kurtosis(s):,.2f}")


def phase_b(df: pd.DataFrame) -> None:
    out("## Phase B - Univariate profiling + distribution shape")
    miss = df.isna().mean().mul(100).round(2)
    out("- missing % by column:")
    out(miss.to_string())

    # B1 Invoice / cancellations
    canc = df["Invoice"].str.startswith("C")
    prefixes = df.loc[df["Invoice"].str[0].str.isalpha(), "Invoice"].str[0].value_counts()
    out(f"\n- B1 Invoice: distinct={df['Invoice'].nunique():,}; "
        f"cancellations(C)={canc.sum():,} ({100*canc.mean():.2f}%); "
        f"letter-prefixes={prefixes.to_dict()}")

    # B2 StockCode
    nonprod = df.loc[~df["StockCode"].str.match(NONPRODUCT), "StockCode"]
    out(f"- B2 StockCode: distinct={df['StockCode'].nunique():,}; "
        f"non-product-format rows={len(nonprod):,}; "
        f"examples={sorted(nonprod.unique())[:15]}")

    # B3 Description
    out(f"- B3 Description: missing={df['Description'].isna().sum():,}; "
        f"distinct={df['Description'].nunique():,}")

    # B4 Quantity, B5 Price (distribution shape)
    out(f"- B4 Quantity: {dist_shape(df['Quantity'])}; "
        f"<=0: {(df['Quantity'] <= 0).sum():,} (neg {(df['Quantity'] < 0).sum():,}, zero {(df['Quantity'] == 0).sum():,})")
    out(f"- B5 Price:    {dist_shape(df['Price'])}; "
        f"<=0: {(df['Price'] <= 0).sum():,} (neg {(df['Price'] < 0).sum():,}, zero {(df['Price'] == 0).sum():,})")

    # B6 temporal balance
    permonth = df.set_index("InvoiceDate").resample("MS").size()
    out(f"- B6 InvoiceDate monthly rows: min={permonth.min():,} max={permonth.max():,} "
        f"(peak {permonth.idxmax():%Y-%m}); months={len(permonth)}")

    # B7 CustomerID
    out(f"- B7 CustomerID: missing={df['CustomerID'].isna().sum():,} "
        f"({100*df['CustomerID'].isna().mean():.2f}%); distinct(non-null)={df['CustomerID'].nunique():,}")

    # B8 Country imbalance
    cc = df["Country"].value_counts(normalize=True)
    hhi = float((cc ** 2).sum())
    out(f"- B8 Country: distinct={df['Country'].nunique()}; top={cc.head(3).round(3).to_dict()}; "
        f"Herfindahl={hhi:.3f} (UK share={cc.get('United Kingdom', float('nan')):.3f})")
    out("")


# --------------------------------------------------------------------------- #
# Phase C - Missingness & duplicates
# --------------------------------------------------------------------------- #
def phase_c(df: pd.DataFrame) -> None:
    out("## Phase C - Missingness & duplicates")
    mid = df["CustomerID"].isna()
    out(f"- C1 missing-CustomerID rows: {mid.sum():,} ({100*mid.mean():.2f}%)")
    out(f"     of those, country breakdown top: {df.loc[mid,'Country'].value_counts().head(3).to_dict()}")
    out(f"- C2 exact duplicate rows: {df.duplicated().sum():,}")
    pc = df.duplicated(subset=["Invoice", "StockCode", "Quantity", "Price"]).sum()
    out(f"- C3 partial duplicates (Invoice+StockCode+Qty+Price): {pc:,}")
    out("")


# --------------------------------------------------------------------------- #
# Phase D - Anomalies + imbalance / concentration
# --------------------------------------------------------------------------- #
def phase_d(df: pd.DataFrame) -> None:
    out("## Phase D - Anomalies + imbalance / concentration diagnostics")
    canc = df["Invoice"].str.startswith("C")
    out(f"- D1 cancellations: C-invoices={canc.sum():,}; negative-qty rows={ (df['Quantity']<0).sum():,}; "
        f"C-invoice rows with negative qty={ (canc & (df['Quantity']<0)).sum():,}")
    out(f"- D2 zero/neg: Quantity<=0={(df['Quantity']<=0).sum():,}; Price<=0={(df['Price']<=0).sum():,}")

    # D3 non-merchandise revenue share (on positive rows)
    pos = df[(df["Quantity"] > 0) & (df["Price"] > 0)].copy()
    pos["rev"] = pos["Quantity"] * pos["Price"]
    nonprod_mask = ~pos["StockCode"].str.match(NONPRODUCT)
    out(f"- D3 non-product-code revenue share: "
        f"{100*pos.loc[nonprod_mask,'rev'].sum()/pos['rev'].sum():.2f}% "
        f"of revenue from {nonprod_mask.sum():,} rows")

    # D4 outliers (describe only)
    out(f"- D4 outliers (DESCRIBE only, NOT removed): "
        f"Quantity p99={pos['Quantity'].quantile(.99):,.0f} max={pos['Quantity'].max():,.0f}; "
        f"Price p99={pos['Price'].quantile(.99):,.2f} max={pos['Price'].max():,.2f}")

    # D5 concentration / imbalance
    cust = pos.groupby("CustomerID")["rev"].sum()
    prod = pos.groupby("StockCode")["rev"].sum()
    invper = pos.groupby("CustomerID")["Invoice"].nunique()
    out("- D5 concentration / imbalance:")
    out(f"    revenue Gini by customer = {gini(cust.values):.3f}")
    out(f"    top-1% customers hold {100*cust.sort_values(ascending=False).head(max(1,len(cust)//100)).sum()/cust.sum():.1f}% of revenue (Pareto)")
    out(f"    revenue Gini by product  = {gini(prod.values):.3f}; top-10 products = {100*prod.sort_values(ascending=False).head(10).sum()/prod.sum():.1f}%")
    out(f"    cancellation ratio (rows) = {100*canc.mean():.2f}%; missing-ID share = {100*df['CustomerID'].isna().mean():.2f}%")
    out(f"    invoices-per-customer: mean={invper.mean():.2f} median={invper.median():.0f} "
        f"skew={skew(invper.values):.2f}; one-time buyers(F=1)={ (invper==1).sum():,} ({100*(invper==1).mean():.1f}%)")
    out("")


# --------------------------------------------------------------------------- #
# Phase E - Cleaning decision log
# --------------------------------------------------------------------------- #
def phase_e(df: pd.DataFrame) -> pd.DataFrame:
    out("## Phase E - Cleaning decision log (ordered rules + reconciliation)")
    n0 = len(df)
    steps = []

    d = df.copy()
    d = d.dropna(subset=["CustomerID"]); steps.append(("1 drop missing CustomerID", len(d)))
    d = d[d["Quantity"] > 0];            steps.append(("2 drop Quantity<=0", len(d)))
    d = d[d["Price"] > 0];               steps.append(("3 drop Price<=0", len(d)))
    d = d.drop_duplicates();             steps.append(("4 drop exact duplicates", len(d)))
    # rule 5: KEEP non-product codes (default) ; rule 6: KEEP outliers (no IQR)
    d["CustomerID"] = d["CustomerID"].astype(int)
    d["Total"] = d["Quantity"] * d["Price"]

    out(f"- starting rows: {n0:,}")
    prev = n0
    for label, m in steps:
        out(f"- rule {label}: {m:,} rows  (removed {prev-m:,})")
        prev = m
    out("- rule 5 non-product StockCodes: KEPT (match papers; impact reported in D3)")
    out("- rule 6 outliers: KEPT (no IQR/clip; graph-paper baseline)")

    # rule 7/8 reconciliation
    line_items = len(d)
    invoices = d["Invoice"].nunique()
    customers = d["CustomerID"].nunique()
    out("\n### Reconciliation (rule 7-8)")
    out(f"- surviving LINE ITEMS : {line_items:,}   (FCA paper: 805,549)")
    out(f"- surviving INVOICES   : {invoices:,}   (Graph paper 'transactions': 79,104)")
    out(f"- CUSTOMERS            : {customers:,}   (both papers: 5,878)  "
        f"{'MATCH' if customers == 5878 else 'CHECK'}")
    out("")
    d.to_parquet(CLEAN_OUT)
    out(f"- saved cleaned transactions -> {CLEAN_OUT}")
    return d


def main() -> None:
    df = phase_a()
    phase_b(df)
    phase_c(df)
    phase_d(df)
    phase_e(df)
    config.TABLES.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(_lines))
    print(f"\n>>> report written to {REPORT}")


if __name__ == "__main__":
    main()
