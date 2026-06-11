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
        CASE
            WHEN r_score >= 4 AND f_score >= 4 THEN 'Champions'
            WHEN r_score = 5 AND f_score IN (1, 2) THEN
                CASE WHEN f_score = 1 THEN 'New Customers' ELSE 'Promising' END
            WHEN r_score = 4 AND f_score = 1 THEN 'Promising'
            WHEN r_score = 4 AND f_score = 2 THEN 'Need Attention'
            WHEN r_score = 3 AND f_score >= 4 THEN 'Loyal Customers'
            WHEN r_score = 3 AND f_score = 3 THEN 'Potential Loyalists'
            WHEN r_score = 3 AND f_score = 2 THEN 'Need Attention'
            WHEN r_score = 3 AND f_score = 1 THEN 'About to Sleep'
            WHEN r_score = 2 AND f_score >= 4 THEN
                CASE WHEN f_score = 5 THEN 'Cannot Lose Them' ELSE 'At Risk' END
            WHEN r_score = 2 AND f_score = 3 THEN 'At Risk'
            WHEN r_score = 2 AND f_score = 2 THEN 'At Risk'
            WHEN r_score = 2 AND f_score = 1 THEN 'About to Sleep'
            WHEN r_score = 1 AND f_score >= 4 THEN 'Cannot Lose Them'
            WHEN r_score = 1 AND f_score = 3 THEN 'Hibernating'
            WHEN r_score <= 2 THEN 'Hibernating'
            ELSE 'Lost'
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