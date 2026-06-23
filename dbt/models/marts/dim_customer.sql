{{ config(materialized='table') }}

-- dim_customer: all unique customers + Unknown (sk=0) for empty customer_id
WITH known AS (
    SELECT
        customer_id,
        MIN(invoice_date) AS first_seen_date
    FROM {{ ref('int_transactions__prepared') }}
    WHERE customer_id != ''
    GROUP BY customer_id
),
all_customers AS (
    -- Unknown customer gets empty string id, then all known customers
    SELECT '' AS customer_id, CAST(NULL AS TIMESTAMP) AS first_seen_date
    UNION ALL
    SELECT customer_id, first_seen_date FROM known
)
SELECT
    -- First row (empty customer_id) gets sk=0, rest get 1, 2, 3...
    ROW_NUMBER() OVER (ORDER BY CASE WHEN c.customer_id = '' THEN 0 ELSE 1 END, c.customer_id) - 1 AS customer_sk,
    c.customer_id,
    c.first_seen_date,
    -- Enrich segment from the RFM mart (mirrors gold_build.py
    -- enrich_dim_customer_with_segment): known customers with RFM get their
    -- segment; sk=0 (Unknown) stays 'Unknown'; customers without RFM stay 'UNKNOWN'.
    COALESCE(r.segment, CASE WHEN c.customer_id = '' THEN 'Unknown' ELSE 'UNKNOWN' END) AS segment
FROM all_customers c
LEFT JOIN {{ ref('mart_rfm') }} r ON c.customer_id = r.customer_id
ORDER BY customer_sk
