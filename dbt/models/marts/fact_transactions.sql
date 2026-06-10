{{ config(materialized='table') }}

-- fact_transactions: join surrogate keys from dimensions
WITH txns AS (
    SELECT
        t.invoice,
        t.stock_code,
        t.customer_id,
        t.country,
        t.quantity,
        t.price,
        t.line_amount,
        CAST(t.invoice_date AS DATE) AS tx_date
    FROM {{ ref('stg_bronze__transactions') }} t
),
with_sk AS (
    SELECT
        ROW_NUMBER() OVER ()      AS transaction_sk,
        COALESCE(c.customer_sk, 0) AS customer_sk,
        p.product_sk,
        cy.country_sk,
        d.date_sk,
        tx.quantity,
        tx.price,
        tx.line_amount
    FROM txns tx
    LEFT JOIN {{ ref('dim_customer') }} c  ON tx.customer_id = c.customer_id
    LEFT JOIN {{ ref('dim_product') }} p   ON tx.stock_code = p.stock_code
    LEFT JOIN {{ ref('dim_country') }} cy  ON tx.country = cy.country_name
    LEFT JOIN {{ ref('dim_date') }} d      ON tx.tx_date = d.date
)
SELECT * FROM with_sk
