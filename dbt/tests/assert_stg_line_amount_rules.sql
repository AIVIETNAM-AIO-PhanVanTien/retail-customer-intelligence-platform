-- Staging line_amount rules:
--   1) line_amount = quantity * price
--   2) negative line_amount only on cancellation rows
select
    invoice,
    stock_code,
    quantity,
    price,
    line_amount,
    is_cancellation
from {{ ref('stg_silver__transactions') }}
where abs(line_amount - quantity * price) > 0.001
   or (
       line_amount < 0
       and coalesce(is_cancellation, false) = false
   )
