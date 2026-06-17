{{ config(materialized='table') }}

-- fact_transactions: full-grain fact (purchases + cancellations) with surrogate keys.
-- is_cancellation is kept as explicit business logic: cancellations are real events
-- (returns) that affect revenue. Do NOT drop them — NET revenue = SUM(line_amount)
-- over the full fact (negatives subtract returns automatically). See PBI measures.
WITH txns AS (
    SELECT
        t.invoice,
        t.stock_code,
        t.customer_id,
        t.country,
        t.quantity,
        t.price,
        t.line_amount,
        t.is_cancellation,
        t.tx_date
    FROM {{ ref('int_transactions__prepared') }} t
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
        tx.line_amount,
        tx.is_cancellation
    FROM txns tx
    LEFT JOIN {{ ref('dim_customer') }} c  ON tx.customer_id = c.customer_id
    LEFT JOIN {{ ref('dim_product') }} p   ON tx.stock_code = p.stock_code
    LEFT JOIN {{ ref('dim_country') }} cy  ON tx.country = cy.country_name
    LEFT JOIN {{ ref('dim_date') }} d      ON tx.tx_date = d.date
)
SELECT * FROM with_sk
