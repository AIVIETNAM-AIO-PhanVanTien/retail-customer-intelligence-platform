{{ config(materialized='table') }}

-- dim_date: unique dates from shifted invoice_date
WITH dates AS (
    SELECT DISTINCT CAST(invoice_date AS DATE) AS dt
    FROM {{ ref('stg_bronze__transactions') }}
)
SELECT
    ROW_NUMBER() OVER (ORDER BY dt)  AS date_sk,
    dt                                AS date,
    YEAR(dt)                          AS year,
    MONTH(dt)                         AS month,
    WEEK(dt)                          AS week,
    DAYOFWEEK(dt)                     AS day_of_week,
    QUARTER(dt)                       AS quarter
FROM dates
ORDER BY dt
