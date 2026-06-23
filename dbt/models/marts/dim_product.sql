{{ config(materialized='table') }}

-- dim_product: unique stock_code (already upper-cased in Bronze)
SELECT
    ROW_NUMBER() OVER (ORDER BY stock_code) AS product_sk,
    stock_code,
    MIN(description) AS description
FROM {{ ref('int_transactions__prepared') }}
GROUP BY stock_code
ORDER BY product_sk
