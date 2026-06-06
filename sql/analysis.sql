-- Data Analysis with SQL  (run against data/processed/retail.db)

-- ===== A1_rfm_score_balance =====
-- RFM(L) score assignment - count of customers per score on each axis (quintiles; should be ~1175-1176 each).
SELECT 'R' AS axis, r_score AS score, COUNT(*) AS customers FROM customer_rfml GROUP BY r_score
        UNION ALL SELECT 'F', f_score, COUNT(*) FROM customer_rfml GROUP BY f_score
        UNION ALL SELECT 'M', m_score, COUNT(*) FROM customer_rfml GROUP BY m_score
        UNION ALL SELECT 'L', l_score, COUNT(*) FROM customer_rfml GROUP BY l_score
        ORDER BY axis, score;

-- ===== A2_segment_sizes_values =====
-- Named RFM segments: size, % of customers, average R/F/M/L, and revenue share.
WITH base AS (
    SELECT *, CAST(ROUND((f_score + m_score) / 2.0) AS INT) AS fm FROM customer_rfml
),
seg AS (
    SELECT *, CASE
        WHEN r_score >= 4 AND fm >= 4 THEN 'Champions'
        WHEN r_score >= 3 AND fm >= 3 THEN 'Loyal Customers'
        WHEN r_score >= 4 AND fm <= 2 THEN 'New / Promising'
        WHEN r_score  = 3 AND fm <= 2 THEN 'Potential Loyalist'
        WHEN r_score  = 2 AND fm >= 3 THEN 'At Risk'
        WHEN r_score  = 1 AND fm >= 4 THEN 'Cannot Lose Them'
        WHEN r_score  = 1 AND fm  = 3 THEN 'At Risk'
        WHEN r_score <= 2 AND fm <= 2 THEN 'Hibernating / Lost'
        ELSE 'Others'
    END AS segment FROM base
)

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

-- ===== A3_churn_by_recency =====
-- Churn risk by recency band: how many customers and how much revenue are at risk.
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

-- ===== A4_response_rate_proxy =====
-- Response rate per segment -- NO campaign-response data exists in Online Retail II, so this reports PROXIES: repeat-purchase rate (frequency>1) and active rate (recency<=90d). Interpret as engagement, not true campaign response.
WITH base AS (
    SELECT *, CAST(ROUND((f_score + m_score) / 2.0) AS INT) AS fm FROM customer_rfml
),
seg AS (
    SELECT *, CASE
        WHEN r_score >= 4 AND fm >= 4 THEN 'Champions'
        WHEN r_score >= 3 AND fm >= 3 THEN 'Loyal Customers'
        WHEN r_score >= 4 AND fm <= 2 THEN 'New / Promising'
        WHEN r_score  = 3 AND fm <= 2 THEN 'Potential Loyalist'
        WHEN r_score  = 2 AND fm >= 3 THEN 'At Risk'
        WHEN r_score  = 1 AND fm >= 4 THEN 'Cannot Lose Them'
        WHEN r_score  = 1 AND fm  = 3 THEN 'At Risk'
        WHEN r_score <= 2 AND fm <= 2 THEN 'Hibernating / Lost'
        ELSE 'Others'
    END AS segment FROM base
)

        SELECT segment,
               COUNT(*)                                                          AS customers,
               ROUND(100.0 * AVG(CASE WHEN frequency > 1 THEN 1 ELSE 0 END), 1)  AS repeat_rate_pct,
               ROUND(100.0 * AVG(CASE WHEN recency <= 90 THEN 1 ELSE 0 END), 1)  AS active_rate_pct
        FROM seg
        GROUP BY segment
        ORDER BY repeat_rate_pct DESC;

-- ===== A5_revenue_concentration =====
-- Revenue concentration by monetary quintile (Pareto check ~ 80/20).
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
