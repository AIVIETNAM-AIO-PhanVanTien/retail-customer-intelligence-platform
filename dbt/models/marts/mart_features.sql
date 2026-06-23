{{ config(materialized='table') }}

-- mart_features: customer-level feature snapshot computed in dbt SQL (DuckDB).
-- Column names are aligned with ml/config.py FEATURE_COLUMNS so this can become a
-- drop-in source for the churn pipeline. Mirrors the feature definitions in
-- ml/features.py (build_customer_features).
--
-- SNAPSHOT SEMANTICS
-- ------------------
-- Computed as-of the latest invoice_date in the data (== "score" mode in
-- ml/features.py). Training-time features use observation_end = max - 90d to
-- leave room for the churn label's evaluation window; those remain in the Python
-- pipeline. This mart is the canonical, testable feature table for scoring / BI
-- / reuse. (To serve training, re-run with a cutoff parameter — deferred.)
--
-- "valid purchase" uses the project's is_valid_purchase flag (customer_id <> ''
-- AND NOT is_cancellation AND line_amount > 0), consistent with mart_rfm /
-- mart_kpi_monthly. It differs from ml/features.py only on the line_amount>0
-- edge case (negligible — Silver guarantees price>0 for non-cancellation rows).
-- Base grain = customers with >=1 valid purchase (matches ml/features.py).

WITH params AS (
    SELECT
        MAX(invoice_date)                                                           AS obs_end,
        MIN(CASE WHEN is_valid_purchase THEN invoice_date END)                      AS obs_min_valid,
        to_timestamp((epoch(MIN(CASE WHEN is_valid_purchase THEN invoice_date END))
                    + epoch(MAX(invoice_date))) / 2.0)                              AS mid_point
    FROM {{ ref('int_transactions__prepared') }}
),
src AS (
    SELECT
        t.customer_id,
        t.invoice,
        t.stock_code,
        t.country,
        CAST(t.quantity AS DOUBLE)   AS quantity,
        CAST(t.price    AS DOUBLE)   AS price,
        CAST(t.line_amount AS DOUBLE) AS line_amount,
        t.invoice_date,
        t.is_cancellation,
        t.is_valid_purchase,
        p.obs_end,
        p.mid_point
    FROM {{ ref('int_transactions__prepared') }} t
    CROSS JOIN params p
    WHERE t.customer_id <> ''
),
-- one row per (customer, invoice) — grain for inter-purchase gap + weekend features
inv AS (
    SELECT customer_id, invoice, MIN(invoice_date) AS invoice_date
    FROM src
    GROUP BY customer_id, invoice
),
inv_meta AS (
    SELECT
        customer_id,
        invoice_date,
        dayofweek(CAST(invoice_date AS DATE))                                                  AS dow,
        (epoch(invoice_date)
            - epoch(lag(invoice_date) OVER (PARTITION BY customer_id ORDER BY invoice_date, invoice))) / 86400.0 AS gap_days
    FROM inv
),
gap_agg AS (
    SELECT
        customer_id,
        AVG(gap_days)       AS avg_gap,
        STDDEV_SAMP(gap_days) AS std_gap
    FROM inv_meta
    WHERE gap_days IS NOT NULL
    GROUP BY customer_id
),
weekend_agg AS (
    SELECT
        customer_id,
        AVG(CASE WHEN dow IN (0, 6) THEN 1.0 ELSE 0.0 END) AS weekend_purchase_ratio
    FROM inv_meta
    GROUP BY customer_id
),
-- monthly revenue per customer for monetary_trend (linear-regression slope)
monthly AS (
    SELECT
        customer_id,
        (year(CAST(invoice_date AS DATE)) * 12 + month(CAST(invoice_date AS DATE))) AS month_index,
        SUM(line_amount) AS monthly_line
    FROM src
    WHERE is_valid_purchase
    GROUP BY customer_id, month_index
),
slope_agg AS (
    SELECT
        customer_id,
        COALESCE(regr_slope(monthly_line, month_index), 0) AS monetary_trend
    FROM monthly
    GROUP BY customer_id
),
inv_value AS (
    SELECT customer_id, invoice, SUM(line_amount) AS invoice_value
    FROM src
    WHERE is_valid_purchase
    GROUP BY customer_id, invoice
),
inv_value_agg AS (
    SELECT
        customer_id,
        MAX(invoice_value) AS max_single_order_value,
        MIN(invoice_value) AS min_single_order_value
    FROM inv_value
    GROUP BY customer_id
),
base AS (
    SELECT
        s.customer_id,
        -- RFM core (valid purchases)
        MAX(CASE WHEN is_valid_purchase THEN invoice_date END)                            AS last_purchase_date,
        MIN(CASE WHEN is_valid_purchase THEN invoice_date END)                            AS first_purchase_date,
        COUNT(DISTINCT CASE WHEN is_valid_purchase THEN invoice END)                      AS frequency,
        SUM(CASE WHEN is_valid_purchase THEN line_amount ELSE 0 END)                      AS monetary,
        SUM(CASE WHEN is_valid_purchase THEN quantity     ELSE 0 END)                     AS total_quantity,
        COUNT(DISTINCT CASE WHEN is_valid_purchase THEN stock_code END)                   AS unique_products,
        SUM(CASE WHEN is_valid_purchase THEN price * quantity ELSE 0 END)                 AS price_quantity_sum,
        -- time-windowed (valid purchases)
        COUNT(DISTINCT CASE WHEN is_valid_purchase AND invoice_date >= s.obs_end - INTERVAL '30 days'  THEN invoice END) AS frequency_last_30d,
        COUNT(DISTINCT CASE WHEN is_valid_purchase AND invoice_date >= s.obs_end - INTERVAL '90 days'  THEN invoice END) AS frequency_last_90d,
        COUNT(DISTINCT CASE WHEN is_valid_purchase AND invoice_date >= s.obs_end - INTERVAL '180 days' THEN invoice END) AS frequency_last_180d,
        SUM(CASE WHEN is_valid_purchase AND invoice_date >= s.obs_end - INTERVAL '90 days' THEN line_amount ELSE 0 END)  AS monetary_last_90d,
        COUNT(DISTINCT CASE WHEN is_valid_purchase AND invoice_date >= s.obs_end - INTERVAL '90 days' THEN stock_code END) AS unique_products_90d,
        -- monetary acceleration halves (valid purchases)
        SUM(CASE WHEN is_valid_purchase AND invoice_date <  s.mid_point THEN line_amount ELSE 0 END) AS monetary_first_half,
        SUM(CASE WHEN is_valid_purchase AND invoice_date >= s.mid_point THEN line_amount ELSE 0 END) AS monetary_second_half,
        -- cancellation / return context (over ALL known-customer rows, incl. cancellations)
        COUNT(DISTINCT invoice)                                                            AS invoice_count,
        COUNT(DISTINCT CASE WHEN is_cancellation THEN invoice END)                         AS cancellation_invoice_count,
        SUM(CASE WHEN quantity > 0 THEN quantity ELSE 0 END)                               AS qty_positive,
        SUM(CASE WHEN quantity < 0 THEN -quantity ELSE 0 END)                              AS qty_returned,
        -- categorical: representative country (MIN = deterministic; ~constant per customer)
        MIN(country)                                                                       AS rep_country
    FROM src s
    GROUP BY s.customer_id
    HAVING COUNT(DISTINCT CASE WHEN is_valid_purchase THEN invoice END) >= 1
)
SELECT
    b.customer_id,
    -- RFM core
    datediff('day', CAST(b.last_purchase_date AS DATE), CAST(p.obs_end AS DATE))                 AS recency_days,
    b.frequency,
    b.monetary,
    b.frequency_last_30d,
    b.frequency_last_90d,
    b.monetary_last_90d,
    COALESCE(b.monetary / NULLIF(b.frequency, 0), 0)                                             AS avg_order_value,
    COALESCE(b.total_quantity / NULLIF(b.frequency, 0), 0)                                       AS avg_basket_size,
    COALESCE(b.price_quantity_sum / NULLIF(b.total_quantity, 0), 0)                              AS avg_unit_price,
    b.total_quantity,
    b.unique_products,
    datediff('day', CAST(b.first_purchase_date AS DATE), CAST(b.last_purchase_date AS DATE))      AS tenure_days,
    COALESCE(g.avg_gap, datediff('day', CAST(b.last_purchase_date AS DATE), CAST(p.obs_end AS DATE))) AS avg_days_between_orders,
    COALESCE(g.std_gap, 0)                                                                       AS std_days_between_orders,
    datediff('day', CAST(b.first_purchase_date AS DATE), CAST(p.obs_end AS DATE))                AS days_since_first_purchase,
    CASE WHEN b.frequency = 1 THEN 1 ELSE 0 END                                                  AS is_one_time_buyer,
    -- engagement
    COALESCE(b.cancellation_invoice_count * 1.0 / NULLIF(b.invoice_count, 0), 0)                 AS cancellation_rate,
    COALESCE(b.qty_returned * 1.0 / NULLIF(b.qty_positive, 0), 0)                                AS return_quantity_rate,
    COALESCE(w.weekend_purchase_ratio, 0)                                                        AS weekend_purchase_ratio,
    COALESCE(sl.monetary_trend, 0)                                                               AS monetary_trend,
    iv.max_single_order_value,
    iv.min_single_order_value,
    COALESCE(b.frequency_last_90d * 1.0 / NULLIF(b.frequency, 0), 0)                             AS ratio_frequency_90d,
    COALESCE(b.frequency_last_180d * 1.0 / NULLIF(b.frequency, 0), 0)                            AS velocity_ratio_180d,
    COALESCE(b.monetary_last_90d / NULLIF(b.monetary, 0), 0)                                     AS spending_recency_ratio,
    COALESCE(b.frequency_last_30d * 1.0 / NULLIF(b.frequency_last_90d + 1, 0), 0)                AS velocity_ratio_30d_90d,
    LEAST(COALESCE(datediff('day', CAST(b.last_purchase_date AS DATE), CAST(p.obs_end AS DATE)) * 1.0
                   / NULLIF(COALESCE(g.avg_gap, datediff('day', CAST(b.last_purchase_date AS DATE), CAST(p.obs_end AS DATE))), 0), 0), 10.0) AS overdue_ratio,
    LEAST(COALESCE(COALESCE(g.std_gap, 0) * 1.0
                   / NULLIF(COALESCE(g.avg_gap, datediff('day', CAST(b.last_purchase_date AS DATE), CAST(p.obs_end AS DATE))), 0), 0), 5.0)  AS purchase_regularity,
    datediff('day', CAST(b.last_purchase_date AS DATE), CAST(p.obs_end AS DATE))
        * CASE WHEN b.frequency = 1 THEN 1 ELSE 0 END                                            AS recency_one_time,
    COALESCE(b.unique_products_90d * 1.0 / NULLIF(b.unique_products, 0), 0)                      AS product_diversity_trend,
    LEAST(COALESCE(b.monetary_second_half / NULLIF(b.monetary_first_half + 1, 0), 0), 20.0)      AS monetary_acceleration,
    CASE WHEN b.rep_country = 'United Kingdom' THEN 1 ELSE 0 END                                 AS is_uk
FROM base b
CROSS JOIN params p
LEFT JOIN gap_agg     g  ON g.customer_id = b.customer_id
LEFT JOIN weekend_agg w  ON w.customer_id = b.customer_id
LEFT JOIN slope_agg   sl ON sl.customer_id = b.customer_id
LEFT JOIN inv_value_agg iv ON iv.customer_id = b.customer_id
