{{ config(materialized='view') }}

-- Intermediate: star-schema-ready transaction grain.
-- Silver owns cleaning/enrichment; this layer adds ONLY what the marts need:
--   - tx_date (DATE)           : for the dim_date join
--   - is_valid_purchase (BOOL) : reusable filter for fact quality + mart_rfm
SELECT
    *,
    CAST(invoice_date AS DATE)                                                    AS tx_date,
    (customer_id <> '' AND is_cancellation = false AND line_amount > 0)           AS is_valid_purchase
FROM {{ ref('stg_silver__transactions') }}
