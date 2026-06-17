{{ config(materialized='table') }}

-- dim_country: unique country values
SELECT
    ROW_NUMBER() OVER (ORDER BY country) AS country_sk,
    country AS country_name
FROM (
    SELECT DISTINCT country
    FROM {{ ref('int_transactions__prepared') }}
) t
ORDER BY country_sk
