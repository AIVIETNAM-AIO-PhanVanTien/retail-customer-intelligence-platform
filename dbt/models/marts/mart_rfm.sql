{{ config(materialized='table') }}

-- mart_rfm: RFM analysis with quintile scoring and segment labels
WITH valid_purchases AS (
    -- Only non-cancellation rows with valid customer and positive line_amount
    SELECT *
    FROM {{ ref('stg_bronze__transactions') }}
    WHERE customer_id != ''
      AND is_cancellation = false
      AND line_amount > 0
),
reference AS (
    SELECT MAX(invoice_date) AS ref_date FROM valid_purchases
),
rfm_agg AS (
    SELECT
        t.customer_id,
        MAX(t.invoice_date)                           AS last_purchase,
        COUNT(DISTINCT t.invoice)                      AS frequency,
        SUM(t.line_amount)                             AS monetary
    FROM valid_purchases t
    GROUP BY t.customer_id
    HAVING SUM(t.line_amount) > 0
),
rfm_recency AS (
    SELECT
        r.*,
        DATE_DIFF('day', r.last_purchase, ref.ref_date) AS recency_days
    FROM rfm_agg r, reference ref
),
scored AS (
    SELECT
        *,
        -- Quintile scoring using NTILE(5) with correct ordering
        -- Recency: fewer days = better score (inverted via DESC)
        NTILE(5) OVER (ORDER BY recency_days DESC)  AS r_score,
        -- Frequency: more = better
        NTILE(5) OVER (ORDER BY frequency ASC)       AS f_score,
        -- Monetary: more = better
        NTILE(5) OVER (ORDER BY monetary ASC)         AS m_score
    FROM rfm_recency
),
segmented AS (
    SELECT
        *,
        -- Mirrors SEGMENT_MAP in src/etl/gold_build.py — keep the two in sync
        CASE
            WHEN (r_score = 5 AND f_score >= 4) OR (r_score = 4 AND f_score = 5) THEN 'Champions'
            WHEN (r_score = 4 AND f_score IN (3, 4)) OR (r_score = 3 AND f_score = 5) THEN 'Loyal Customers'
            WHEN r_score = 3 AND f_score IN (3, 4) THEN 'Potential Loyalists'
            WHEN r_score = 5 AND f_score = 1 THEN 'New Customers'
            WHEN (r_score = 5 AND f_score = 2) OR (r_score = 4 AND f_score = 1) THEN 'Promising'
            WHEN (r_score = 2 AND f_score = 5) OR (r_score = 1 AND f_score >= 4) THEN 'Cannot Lose Them'
            WHEN r_score = 2 AND f_score IN (2, 3, 4) THEN 'At Risk'
            WHEN r_score IN (2, 3) AND f_score = 1 THEN 'About to Sleep'
            WHEN r_score = 1 AND f_score IN (2, 3) THEN 'Hibernating'
            WHEN r_score = 1 AND f_score = 1 THEN 'Lost'
            ELSE 'Need Attention'
        END AS segment
    FROM scored
)
SELECT
    customer_id,
    recency_days,
    frequency,
    monetary,
    r_score,
    f_score,
    m_score,
    segment
FROM segmented
ORDER BY customer_id