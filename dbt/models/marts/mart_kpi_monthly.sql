{{ config(materialized='table') }}

-- mart_kpi_monthly: aggregate business KPIs at year_month grain.
-- Single source of truth: int_transactions__prepared (which mirrors Silver).
--
-- Definitions
-- -----------
--   valid purchase = customer_id <> '' AND is_cancellation = false AND line_amount > 0
--   revenue        = SUM(line_amount) over valid purchases (gross of returns)
--   units_sold     = SUM(quantity)    over valid purchases
--   orders         = COUNT(DISTINCT invoice) over valid purchases
--   active_customers = COUNT(DISTINCT customer_id) over valid purchases
--   aov            = revenue / orders
--   net_revenue    = revenue + cancellation_value
--                    (cancellation_value is normally negative, so returns subtract;
--                     the anomaly C496350 adds +373.57 here — see note below)
--   cancellation_order_rate = cancelled_orders / (orders + cancelled_orders)
--
-- Data-quality note
-- -----------------
-- Invoice C496350 (stock_code M, a "Manual" adjustment) is a cancellation row with
-- POSITIVE quantity/line_amount (+1, +£373.57) — a known data anomaly under QA
-- review (caught by assert_*_cancellation_consistency at severity=warn). It is NOT
-- filtered here, per QA's ownership of data validation. It is excluded from
-- `revenue`/`units_sold`/`orders` (valid-purchase only) but flows into the
-- cancellation aggregates (cancelled_orders, cancellation_value) as-is.
WITH base AS (
    SELECT
        year_month,
        customer_id,
        invoice,
        quantity,
        line_amount,
        is_cancellation,
        is_valid_purchase
    FROM {{ ref('int_transactions__prepared') }}
),
agg AS (
    SELECT
        year_month,
        SUM(CASE WHEN is_valid_purchase THEN line_amount ELSE 0 END)        AS revenue,
        SUM(CASE WHEN is_valid_purchase THEN quantity     ELSE 0 END)       AS units_sold,
        COUNT(DISTINCT CASE WHEN is_valid_purchase THEN invoice END)        AS orders,
        COUNT(DISTINCT CASE WHEN is_valid_purchase THEN customer_id END)    AS active_customers,
        COUNT(DISTINCT CASE WHEN is_cancellation    THEN invoice END)       AS cancelled_orders,
        SUM(CASE WHEN is_cancellation THEN line_amount ELSE 0 END)          AS cancellation_value,
        COUNT(*)                                                            AS line_count
    FROM base
    GROUP BY year_month
)
SELECT
    year_month,
    revenue,
    units_sold,
    orders,
    active_customers,
    CASE WHEN orders > 0 THEN ROUND(revenue / orders, 4) ELSE NULL END                       AS aov,
    cancelled_orders,
    cancellation_value,
    revenue + cancellation_value                                                             AS net_revenue,
    CASE WHEN (orders + cancelled_orders) > 0
         THEN ROUND(cancelled_orders * 1.0 / (orders + cancelled_orders), 4)
         ELSE NULL END                                                                       AS cancellation_order_rate,
    line_count
FROM agg
ORDER BY year_month
