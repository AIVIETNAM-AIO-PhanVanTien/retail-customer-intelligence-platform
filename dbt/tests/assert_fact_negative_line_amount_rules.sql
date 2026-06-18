-- Negative line_amount allowed only on cancellation rows
select
    transaction_sk,
    quantity,
    price,
    line_amount,
    is_cancellation
from {{ ref('fact_transactions') }}
where line_amount < 0
  and coalesce(is_cancellation, false) = false
