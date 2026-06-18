-- D3: staging must not contain full-row duplicates after DISTINCT
select
    invoice,
    stock_code,
    description,
    quantity,
    price,
    customer_id,
    country,
    is_cancellation,
    invoice_date,
    count(*) as duplicate_count
from {{ ref('stg_silver__transactions') }}
group by 1, 2, 3, 4, 5, 6, 7, 8, 9
having count(*) > 1
