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
    ROW_NUMBER() OVER (ORDER BY CASE WHEN customer_id = '' THEN 0 ELSE 1 END, customer_id) - 1 AS customer_sk,
    customer_id,
    first_seen_date,
    CASE WHEN customer_id = '' THEN 'Unknown' ELSE 'UNKNOWN' END AS segment
FROM all_customers
ORDER BY customer_sk
