-- fact_transactions: price must not be negative
select
    transaction_sk,
    quantity,
    price,
    line_amount
from {{ ref('fact_transactions') }}
where price < 0
