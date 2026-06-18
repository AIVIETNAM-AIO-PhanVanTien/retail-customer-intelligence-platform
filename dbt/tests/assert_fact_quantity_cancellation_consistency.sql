-- quantity < 0 iff is_cancellation on fact
select
    transaction_sk,
    quantity,
    line_amount,
    is_cancellation
from {{ ref('fact_transactions') }}
where (quantity < 0 and coalesce(is_cancellation, false) = false)
   or (coalesce(is_cancellation, false) = true and quantity >= 0)
