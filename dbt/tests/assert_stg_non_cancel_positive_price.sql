-- Non-cancellation rows must have price > 0 (noise filter at silver_transform)
select
    invoice,
    stock_code,
    quantity,
    price,
    is_cancellation
from {{ ref('stg_silver__transactions') }}
where coalesce(is_cancellation, false) = false
  and price <= 0
