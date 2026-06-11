{{ config(materialized='view') }}

-- Staging: read Bronze Parquet, compute line_amount, filter noise
-- Dedup is handled by DISTINCT (keeps one copy of each duplicate)
WITH raw AS (
    SELECT * FROM read_parquet('../data/bronze/year_month=*/data.parquet',
                               filename=false, hive_partitioning=false)
),
deduped AS (
    SELECT DISTINCT * FROM raw
),
with_line_amount AS (
    SELECT
        *,
        quantity * price AS line_amount,
    FROM deduped
),
cleaned AS (
    SELECT *
    FROM with_line_amount
    WHERE
        -- Noise filter: remove non-cancellation rows with price <= 0
        NOT (is_cancellation = false AND price <= 0)
)
SELECT
    invoice,
    stock_code,
    description,
    quantity,
    price,
    customer_id,
    country,
    is_cancellation,
    line_amount,
    invoice_date,
    original_invoice_date,
    YEAR(invoice_date)       AS invoice_year,
    MONTH(invoice_date)      AS invoice_month,
    DAY(invoice_date)        AS invoice_day,
    QUARTER(invoice_date)    AS invoice_quarter,
    DAYOFWEEK(invoice_date)  AS invoice_day_of_week,
    WEEK(invoice_date)       AS invoice_week,
    STRFTIME(invoice_date, '%Y-%m') AS year_month
FROM cleaned
