{{ config(materialized='table') }}

-- dim_country: unique country values
SELECT
    ROW_NUMBER() OVER (ORDER BY country) AS country_sk,
    country AS country_name
FROM (
    SELECT DISTINCT country
    FROM {{ ref('stg_bronze__transactions') }}
) t
ORDER BY country_sk
