{{ config(materialized='table') }}

-- dim_date: unique dates from shifted invoice_date
WITH dates AS (
    SELECT DISTINCT tx_date AS dt
    FROM {{ ref('int_transactions__prepared') }}
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
