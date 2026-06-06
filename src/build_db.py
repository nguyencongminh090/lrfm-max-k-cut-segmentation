"""Build the SQLite relational layer (3NF) from the cleaned transactions.

Fully-normalized schema with declared PRIMARY KEY / FOREIGN KEY constraints
(foreign-key enforcement ON):

    dim_customer (customer_id PK, country)
    dim_product  (stock_code  PK, description)
    dim_invoice  (invoice_id  PK, customer_id FK->dim_customer, invoice_date)
    fact_line    (line_id PK, invoice_id FK->dim_invoice, stock_code FK->dim_product,
                  quantity, price)                         -- NO derived line_total
    v_invoices   VIEW(invoice_id, customer_id, invoice_date, invoice_total)
    customer_rfml TABLE  -- SQL is the SOURCE OF TRUTH for R/F/M/L + 1..5 scores

Why this is 3NF (vs the earlier star `fact_sales`):
  * invoice-level attributes (customer_id, invoice_date) now live once per invoice
    in dim_invoice -> removes the 2NF partial dependency on invoice_id.
  * line_total is computed (quantity*price), never stored -> removes the 3NF
    derived-column redundancy.
  * fact_line has a surrogate PK (line_id) -> a real key for the line grain.

Run:  python -m src.build_db
"""
from __future__ import annotations

import sqlite3
import pandas as pd

from . import config

CLEAN = config.DATA_PROCESSED / "transactions_clean.parquet"

SCHEMA = """
CREATE TABLE dim_customer (
    customer_id INTEGER PRIMARY KEY,
    country     TEXT
);
CREATE TABLE dim_product (
    stock_code  TEXT PRIMARY KEY,
    description TEXT
);
CREATE TABLE dim_invoice (
    invoice_id   TEXT    PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES dim_customer(customer_id),
    invoice_date TEXT    NOT NULL
);
CREATE TABLE fact_line (
    line_id    INTEGER PRIMARY KEY,
    invoice_id TEXT    NOT NULL REFERENCES dim_invoice(invoice_id),
    stock_code TEXT    NOT NULL REFERENCES dim_product(stock_code),
    quantity   INTEGER NOT NULL,
    price      REAL    NOT NULL
);
"""

# customer_rfml: monetary is COMPUTED from fact_line (no stored line_total);
# dates/customer come from dim_invoice. Same R/F/M/L as before, now from 3NF tables.
SQL_CUSTOMER_RFML = """
DROP TABLE IF EXISTS customer_rfml;
CREATE TABLE customer_rfml AS
WITH snap AS (SELECT MAX(invoice_date) AS snapshot FROM dim_invoice),
line AS (
    SELECT di.customer_id, di.invoice_id, di.invoice_date,
           f.quantity * f.price AS amount
    FROM fact_line f
    JOIN dim_invoice di ON f.invoice_id = di.invoice_id
),
agg AS (
    SELECT customer_id,
        CAST(julianday(date((SELECT snapshot FROM snap))) - julianday(date(MAX(invoice_date))) AS INT) AS recency,
        COUNT(DISTINCT invoice_id) AS frequency,
        ROUND(SUM(amount), 2)      AS monetary,
        CAST(julianday(date(MAX(invoice_date))) - julianday(date(MIN(invoice_date))) AS INT) AS length
    FROM line
    GROUP BY customer_id
)
SELECT
    customer_id, recency, frequency, monetary, length,
    NTILE(5) OVER (ORDER BY recency   DESC, customer_id) AS r_score,
    NTILE(5) OVER (ORDER BY frequency ASC,  customer_id) AS f_score,
    NTILE(5) OVER (ORDER BY monetary  ASC,  customer_id) AS m_score,
    NTILE(5) OVER (ORDER BY length    ASC,  customer_id) AS l_score
FROM agg;
"""


def _load_clean() -> pd.DataFrame:
    df = pd.read_parquet(CLEAN).rename(columns={
        "Invoice": "invoice_id", "StockCode": "stock_code",
        "CustomerID": "customer_id", "Quantity": "quantity",
        "Price": "price", "Description": "description", "Country": "country",
    })
    df["invoice_date"] = pd.to_datetime(df["InvoiceDate"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    return df


def _mode(s: pd.Series):
    """Most-frequent non-null value, or None if all null."""
    s = s.dropna()
    return s.value_counts().index[0] if len(s) else None


def build() -> None:
    df = _load_clean()
    config.SQLITE_DB.unlink(missing_ok=True)
    con = sqlite3.connect(config.SQLITE_DB)
    con.execute("PRAGMA foreign_keys = ON")     # enforce referential integrity
    con.executescript(SCHEMA)

    # --- build dimension/fact frames (3NF) ---
    dim_customer = (df.groupby("customer_id")["country"].agg(_mode)
                      .reset_index())
    dim_product = (df.groupby("stock_code")["description"].agg(_mode)   # ALL codes (FK target)
                     .reset_index())
    dim_invoice = (df.groupby("invoice_id")
                     .agg(customer_id=("customer_id", "first"),
                          invoice_date=("invoice_date", "min"))
                     .reset_index())
    fact_line = df[["invoice_id", "stock_code", "quantity", "price"]]

    # --- insert in FK order (parents before children) ---
    dim_customer.to_sql("dim_customer", con, index=False, if_exists="append")
    dim_product.to_sql("dim_product", con, index=False, if_exists="append")
    dim_invoice.to_sql("dim_invoice", con, index=False, if_exists="append")
    fact_line.to_sql("fact_line", con, index=False, if_exists="append", chunksize=50_000)

    # --- indexes / view / rfml ---
    con.executescript("""
        CREATE INDEX ix_inv_customer  ON dim_invoice(customer_id);
        CREATE INDEX ix_line_invoice  ON fact_line(invoice_id);
        CREATE INDEX ix_line_stock    ON fact_line(stock_code);
        DROP VIEW IF EXISTS v_invoices;
        CREATE VIEW v_invoices AS
            SELECT di.invoice_id, di.customer_id, di.invoice_date,
                   ROUND(SUM(f.quantity * f.price), 2) AS invoice_total
            FROM dim_invoice di JOIN fact_line f ON f.invoice_id = di.invoice_id
            GROUP BY di.invoice_id, di.customer_id, di.invoice_date;
    """)
    con.executescript(SQL_CUSTOMER_RFML)
    con.execute("CREATE UNIQUE INDEX ix_rfml_customer ON customer_rfml(customer_id)")
    con.commit()
    _check_fk(con)
    _report(con)
    con.close()
    print(f"\n>>> 3NF SQLite DB written to {config.SQLITE_DB}")


def _check_fk(con) -> None:
    bad = con.execute("PRAGMA foreign_key_check").fetchall()
    print(f"=== referential integrity: {'OK (no FK violations)' if not bad else f'{len(bad)} VIOLATIONS'} ===")


def _report(con) -> None:
    q = lambda s: pd.read_sql_query(s, con)
    print("\n=== row counts ===")
    for t in ("dim_customer", "dim_product", "dim_invoice", "fact_line", "customer_rfml"):
        print(f"  {t:14} {q(f'SELECT COUNT(*) n FROM {t}').n[0]:>9,}")
    print(f"  v_invoices     {q('SELECT COUNT(*) n FROM v_invoices').n[0]:>9,}")

    print("\n=== RFM(L) reconciliation vs graph paper (Table 1) ===")
    m = q("""SELECT COUNT(*) customers, ROUND(AVG(recency),2) r_mean,
                    ROUND(AVG(frequency),2) f_mean, ROUND(AVG(monetary),2) m_mean,
                    ROUND(AVG(length),2) l_mean FROM customer_rfml""")
    print(m.to_string(index=False))
    print("  expected: customers=5878  r_mean~200.87  f_mean~6.30  m_mean~2965.56")

    rfm = q("SELECT COUNT(*) n FROM (SELECT DISTINCT r_score,f_score,m_score FROM customer_rfml)").n[0]
    lrfm = q("SELECT COUNT(*) n FROM (SELECT DISTINCT l_score,r_score,f_score,m_score FROM customer_rfml)").n[0]
    print(f"\n  distinct (R,F,M) cells   = {rfm}  (<= 125)")
    print(f"  distinct (L,R,F,M) cells = {lrfm}  (<= 625)")


if __name__ == "__main__":
    build()
