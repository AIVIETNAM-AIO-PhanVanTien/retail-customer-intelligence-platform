{{ config(materialized='view') }}

-- Staging: 1:1 mirror of the validated Silver layer.
-- Silver (Python: src/etl/silver_transform.py) already:
--   - deduplicated rows
--   - computed line_amount = quantity * price
--   - filtered non-cancellation rows with price <= 0 (noise)
--   - derived calendar columns (invoice_year/month/quarter/week/day_of_week)
-- So this model is a thin, explicitly-typed projection — no re-cleaning.
SELECT
    invoice,
    stock_code,
    description,
    CAST(quantity AS DOUBLE)              AS quantity,
    CAST(price AS DOUBLE)                 AS price,
    customer_id,
    country,
    CAST(is_cancellation AS BOOLEAN)      AS is_cancellation,
    CAST(line_amount AS DOUBLE)           AS line_amount,
    CAST(invoice_date AS TIMESTAMP)       AS invoice_date,
    CAST(original_invoice_date AS TIMESTAMP) AS original_invoice_date,
    invoice_year,
    invoice_month,
    invoice_day,
    invoice_quarter,
    invoice_day_of_week,
    invoice_week,
    year_month
FROM read_parquet('../data/silver/year_month=*/data_silver.parquet',
                  filename=false, hive_partitioning=false)
