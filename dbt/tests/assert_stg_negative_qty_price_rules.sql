{{ config(severity='warn') }}

-- quantity < 0 iff is_cancellation (bidirectional rule).
-- WARN severity: see assert_fact_quantity_cancellation_consistency — the single
-- anomaly (invoice C496350) is real data under QA review; surfaced but non-blocking.
-- 1) negative qty only on cancellations
-- 2) cancellations must have negative qty
select
    invoice,
    stock_code,
    quantity,
    price,
    is_cancellation
from {{ ref('stg_silver__transactions') }}
where price < 0
   or (quantity < 0 and is_cancellation = false)
   or (is_cancellation = true and quantity >= 0)
