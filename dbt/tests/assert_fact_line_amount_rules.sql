-- Fact line_amount rules (mirror staging):
--   1) line_amount = quantity * price
--   2) negative line_amount only on cancellation rows
select
    transaction_sk,
    quantity,
    price,
    line_amount,
    is_cancellation
from {{ ref('fact_transactions') }}
where abs(line_amount - quantity * price) > 0.001
   or (
       line_amount < 0
       and coalesce(is_cancellation, false) = false
   )
