{{ config(materialized='table') }}

-- dim_product: unique stock_code (already upper-cased in Bronze)
SELECT
    ROW_NUMBER() OVER (ORDER BY stock_code) AS product_sk,
    stock_code,
    description
FROM (
    SELECT DISTINCT
        stock_code,
        FIRST(description) OVER (PARTITION BY stock_code ORDER BY description) AS description
    FROM {{ ref('stg_bronze__transactions') }}
) t
ORDER BY product_sk
