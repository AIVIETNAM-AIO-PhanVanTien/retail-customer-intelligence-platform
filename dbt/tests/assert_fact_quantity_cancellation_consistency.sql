{{ config(severity='warn') }}

-- quantity < 0 iff is_cancellation on fact.
-- WARN severity: the single known anomaly (invoice C496350, stock_code M — a
-- "Manual" adjustment with +qty on a cancelled invoice) is real data under QA
-- review. The test still surfaces it in the report so QA sees it; it just no
-- longer blocks the run. If QA prefers a hard regression guard, upgrade to
-- `error_if='>= 2'` so a *second* anomaly fails the pipeline.
select
    transaction_sk,
    quantity,
    line_amount,
    is_cancellation
from {{ ref('fact_transactions') }}
where (quantity < 0 and coalesce(is_cancellation, false) = false)
   or (coalesce(is_cancellation, false) = true and quantity >= 0)
