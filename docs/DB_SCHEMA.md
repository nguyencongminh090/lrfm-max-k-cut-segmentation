# Database Schema, E/R & Normalization (3NF)

The SQLite layer (`data/processed/retail.db`, built by `src/build_db.py`) is a
**fully-normalized (3NF) relational schema** with declared PRIMARY KEY / FOREIGN
KEY constraints and FK enforcement ON. (It started as a denormalized star with a
single `fact_sales` table; we refactored to 3NF — see §5 for the history/trade-off.)

## 1. E/R diagram

```
   dim_customer                                   dim_product
 ┌────────────────┐                            ┌──────────────────┐
 │ customer_id PK │                             │ stock_code   PK  │
 │ country        │                             │ description      │
 └───────┬────────┘                             └────────┬─────────┘
       1 │                                                │ 1
         │                                                │
         │ ┌───────────────────┐        ┌─────────────────┴─────┐
       * │ │   dim_invoice     │      * │       fact_line        │ *
         └─┤ invoice_id   PK   ├────────┤ line_id     PK         ├──┘
           │ customer_id  FK   │  1   * │ invoice_id  FK→invoice │
           │ invoice_date      │        │ stock_code  FK→product │
           └─────────┬─────────┘        │ quantity               │
                     │                  │ price                  │
                     │                  └───────────┬────────────┘
                     │   aggregated (quantity*price)│
              ┌──────┴───────────────┐      ┌───────┴──────────────────┐
              ▼                       ▼      ▼                          ▼
        v_invoices (VIEW)                   customer_rfml (TABLE)
   invoice_id, customer_id,            customer_id PK, recency,frequency,
   invoice_date, invoice_total         monetary,length, r/f/m/l_score
```

Cardinality:
- `dim_customer 1 ──< dim_invoice` (a customer has many invoices)
- `dim_invoice 1 ──< fact_line`    (an invoice has many line items)
- `dim_product 1 ──< fact_line`    (a product appears on many lines)
- `v_invoices`, `customer_rfml` are **derived** (aggregations); not base tables.

## 2. Keys & functional dependencies

| Table | PK | FKs | FDs |
|---|---|---|---|
| `dim_customer` | customer_id | — | customer_id → country |
| `dim_product`  | stock_code  | — | stock_code → description |
| `dim_invoice`  | invoice_id  | customer_id→dim_customer | invoice_id → customer_id, invoice_date |
| `fact_line`    | line_id (surrogate) | invoice_id→dim_invoice, stock_code→dim_product | line_id → invoice_id, stock_code, quantity, price |
| `customer_rfml`| customer_id | — | customer_id → recency,frequency,monetary,length,scores |

## 3. Normalization analysis — now every table is 3NF

- **1NF:** all columns atomic, no repeating groups. ✓ (all tables)
- **2NF:** no non-key attribute depends on *part* of a composite key. The old
  `fact_sales` violated this — `customer_id`/`invoice_date` depended on
  `invoice_id` alone (part of the `(invoice_id, stock_code)` key). Now those live
  once in **`dim_invoice`**, and `fact_line` uses a single-attribute surrogate key
  `line_id`, so there is **no partial dependency**. ✓
- **3NF:** no transitive / derived non-key dependency. The old `line_total =
  quantity × price` was a stored derived column; it is **dropped** and computed on
  demand (in `v_invoices` and `customer_rfml`). ✓
- **BCNF:** every determinant is a candidate key — holds for all four base tables
  (each FD's left side is the PK). ✓

`customer_rfml` is a **materialized aggregate "mart"** (its values are aggregates
of `fact_line` + global-quantile scores). Structurally it is 3NF (customer_id →
all columns); it is intentionally materialized for the modeling step.

Referential integrity is **enforced** (`PRAGMA foreign_keys = ON`); the build runs
`PRAGMA foreign_key_check` and reports **no violations**.

## 4. Verification (the refactor is lossless)
Rebuilding in 3NF reproduced the **exact same** features as the star version:
customers = 5,878, recency mean = 200.87, frequency mean = 6.29, distinct
(R,F,M) cells = 114, (L,R,F,M) = 313. Normalizing changed the *storage*, not the
*information*.

## 5. History & trade-off (why we still could have kept the star)
The initial design was a star with one `fact_sales` line-item table — deliberately
denormalized so analysts slice without joins (standard for OLAP/Tableau). We moved
to 3NF on request. The trade-off:

| | Star (initial) | **3NF (current)** |
|---|---|---|
| Redundancy | invoice attrs repeated per line | minimal |
| Update anomalies | possible | avoided |
| Analytics queries | fewer joins | customer RFM needs `fact_line ⋈ dim_invoice` |
| Integrity | logical only | **PK/FK enforced** |

For a pure dashboard workload the star is fine; the 3NF design is stricter and
safer (enforced integrity, no derived/duplicated data) at the cost of a join when
aggregating to the customer grain — which `v_invoices` and `customer_rfml`
encapsulate anyway.
