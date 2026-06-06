"""Data Analysis with SQL (project deliverable) on the 3NF retail.db.

Covers the brief's SQL tasks:
  A1  RFM score assignment & balance (quintiles via NTILE, already in customer_rfml)
  A2  Named RFM segments: sizes, avg R/F/M/L, revenue share   (segment sizes & avg values)
  A3  Churn risk by recency bands                              (churn risk by recency)
  A4  "Response rate per segment" -> PROXY (no campaign-response data in the dataset)
  A5  Revenue concentration by monetary quintile (Pareto)

Runs each query against data/processed/retail.db, prints results, writes
results/tables/sql_analysis_report.md, and dumps the portable sql/analysis.sql.

Run:  python -m src.sql_analysis
"""
from __future__ import annotations

import sqlite3
import pandas as pd

from . import config

REPORT = config.TABLES / "sql_analysis_report.md"
SQL_FILE = config.ROOT / "sql" / "analysis.sql"

# Standard RFM segment grid on R-score and a combined FM-score (first match wins).
SEGMENT_CASE = """CASE
        WHEN r_score >= 4 AND fm >= 4 THEN 'Champions'
        WHEN r_score >= 3 AND fm >= 3 THEN 'Loyal Customers'
        WHEN r_score >= 4 AND fm <= 2 THEN 'New / Promising'
        WHEN r_score  = 3 AND fm <= 2 THEN 'Potential Loyalist'
        WHEN r_score  = 2 AND fm >= 3 THEN 'At Risk'
        WHEN r_score  = 1 AND fm >= 4 THEN 'Cannot Lose Them'
        WHEN r_score  = 1 AND fm  = 3 THEN 'At Risk'
        WHEN r_score <= 2 AND fm <= 2 THEN 'Hibernating / Lost'
        ELSE 'Others'
    END"""

_SEG_BASE = f"""
WITH base AS (
    SELECT *, CAST(ROUND((f_score + m_score) / 2.0) AS INT) AS fm FROM customer_rfml
),
seg AS (
    SELECT *, {SEGMENT_CASE} AS segment FROM base
)
"""

QUERIES: dict[str, tuple[str, str]] = {

    "A1_rfm_score_balance": (
        "RFM(L) score assignment - count of customers per score on each axis "
        "(quintiles; should be ~1175-1176 each).",
        """
        SELECT 'R' AS axis, r_score AS score, COUNT(*) AS customers FROM customer_rfml GROUP BY r_score
        UNION ALL SELECT 'F', f_score, COUNT(*) FROM customer_rfml GROUP BY f_score
        UNION ALL SELECT 'M', m_score, COUNT(*) FROM customer_rfml GROUP BY m_score
        UNION ALL SELECT 'L', l_score, COUNT(*) FROM customer_rfml GROUP BY l_score
        ORDER BY axis, score;
        """,
    ),

    "A2_segment_sizes_values": (
        "Named RFM segments: size, % of customers, average R/F/M/L, and revenue share.",
        _SEG_BASE + """
        SELECT segment,
               COUNT(*)                                                   AS customers,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)         AS pct_customers,
               ROUND(AVG(recency), 0)                                     AS avg_recency,
               ROUND(AVG(frequency), 1)                                   AS avg_frequency,
               ROUND(AVG(monetary), 0)                                    AS avg_monetary,
               ROUND(AVG(length), 0)                                      AS avg_length,
               ROUND(SUM(monetary), 0)                                    AS total_revenue,
               ROUND(100.0 * SUM(monetary) / SUM(SUM(monetary)) OVER (), 1) AS pct_revenue
        FROM seg
        GROUP BY segment
        ORDER BY total_revenue DESC;
        """,
    ),

    "A3_churn_by_recency": (
        "Churn risk by recency band: how many customers and how much revenue are at risk.",
        """
        WITH band AS (
            SELECT *, CASE
                WHEN recency <=  90 THEN '1 Active (<=90d)'
                WHEN recency <= 180 THEN '2 Cooling (91-180d)'
                WHEN recency <= 365 THEN '3 At Risk (181-365d)'
                ELSE                     '4 Churned (>365d)'
            END AS churn_band
            FROM customer_rfml
        )
        SELECT churn_band,
               COUNT(*)                                                   AS customers,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)         AS pct_customers,
               ROUND(AVG(frequency), 1)                                   AS avg_frequency,
               ROUND(SUM(monetary), 0)                                    AS revenue_at_band,
               ROUND(100.0 * SUM(monetary) / SUM(SUM(monetary)) OVER (), 1) AS pct_revenue
        FROM band
        GROUP BY churn_band
        ORDER BY churn_band;
        """,
    ),

    "A4_response_rate_proxy": (
        "Response rate per segment -- NO campaign-response data exists in Online "
        "Retail II, so this reports PROXIES: repeat-purchase rate (frequency>1) and "
        "active rate (recency<=90d). Interpret as engagement, not true campaign response.",
        _SEG_BASE + """
        SELECT segment,
               COUNT(*)                                                          AS customers,
               ROUND(100.0 * AVG(CASE WHEN frequency > 1 THEN 1 ELSE 0 END), 1)  AS repeat_rate_pct,
               ROUND(100.0 * AVG(CASE WHEN recency <= 90 THEN 1 ELSE 0 END), 1)  AS active_rate_pct
        FROM seg
        GROUP BY segment
        ORDER BY repeat_rate_pct DESC;
        """,
    ),

    "A5_revenue_concentration": (
        "Revenue concentration by monetary quintile (Pareto check ~ 80/20).",
        """
        WITH ranked AS (
            SELECT monetary, NTILE(5) OVER (ORDER BY monetary DESC) AS m_quintile
            FROM customer_rfml
        )
        SELECT m_quintile,
               COUNT(*)                                                   AS customers,
               ROUND(SUM(monetary), 0)                                    AS total_revenue,
               ROUND(100.0 * SUM(monetary) / SUM(SUM(monetary)) OVER (), 1) AS pct_revenue
        FROM ranked
        GROUP BY m_quintile
        ORDER BY m_quintile;
        """,
    ),
}

_lines: list[str] = []


def out(s="") -> None:
    print(s)
    _lines.append(str(s))


def main() -> None:
    con = sqlite3.connect(config.SQLITE_DB)
    out("# Data Analysis with SQL - report\n")
    out(f"SQLite {sqlite3.sqlite_version}; source: {config.SQLITE_DB.name} (3NF schema)\n")

    sql_dump = ["-- Data Analysis with SQL  (run against data/processed/retail.db)\n"]
    for name, (desc, sql) in QUERIES.items():
        out(f"\n## {name}")
        out(f"_{desc}_\n")
        df = pd.read_sql_query(sql, con)
        out("```")
        out(df.to_string(index=False))
        out("```")
        sql_dump.append(f"-- ===== {name} =====\n-- {desc}\n{sql.strip()}\n")

    con.close()
    config.TABLES.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(_lines))
    SQL_FILE.parent.mkdir(parents=True, exist_ok=True)
    SQL_FILE.write_text("\n".join(sql_dump))
    print(f"\n>>> report  -> {REPORT}")
    print(f">>> queries -> {SQL_FILE}")


if __name__ == "__main__":
    main()
