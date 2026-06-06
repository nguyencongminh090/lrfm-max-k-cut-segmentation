"""Load and preprocess the Online Retail II dataset.

Reproduces the preprocessing in Corrêa Vianna Filho et al. (2026, Sec. 4.2):
    - drop rows with missing Customer ID
    - drop negative Quantity and/or Price
    - drop duplicate records
    - KEEP extreme values (no outlier removal) -- intentional, see paper.
Target after cleaning (their report): ~79,104 transactions, 5878 customers.
"""
from __future__ import annotations

import pandas as pd

from . import config


def load_raw(path=config.RAW_RETAIL_FILE) -> pd.DataFrame:
    """Read the raw Online Retail II workbook (both sheets) into one frame.

    The UCI .xlsx has two sheets: 'Year 2009-2010' and 'Year 2010-2011'.
    """
    # TODO: confirm exact sheet names once the file is downloaded.
    sheets = pd.read_excel(path, sheet_name=None)  # dict of all sheets
    df = pd.concat(sheets.values(), ignore_index=True)
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the paper's cleaning steps. Returns the cleaned transaction frame."""
    df = df.copy()
    df.columns = [c.strip().replace(" ", "") for c in df.columns]
    # Expected columns: Invoice, StockCode, Description, Quantity,
    #                   InvoiceDate, Price, CustomerID, Country
    df = df.dropna(subset=["CustomerID"])
    df = df[(df["Quantity"] > 0) & (df["Price"] > 0)]
    df = df.drop_duplicates()
    df["CustomerID"] = df["CustomerID"].astype(int)
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    df["Total"] = df["Quantity"] * df["Price"]
    return df


def get_clean(force: bool = False) -> pd.DataFrame:
    """Cached entry point: build once, reuse the parquet on subsequent runs."""
    cache = config.DATA_PROCESSED / "transactions_clean.parquet"
    if cache.exists() and not force:
        return pd.read_parquet(cache)
    df = clean(load_raw())
    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache)
    return df


if __name__ == "__main__":
    d = get_clean(force=True)
    print(f"clean transactions: {len(d):,}  |  unique customers: {d['CustomerID'].nunique():,}")
