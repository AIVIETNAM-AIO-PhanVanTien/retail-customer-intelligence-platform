-- fact_transactions: no null on PK, FKs, or measure columns
select
    transaction_sk,
    customer_sk,
    product_sk,
    country_sk,
    date_sk,
    quantity,
    price,
    line_amount
from {{ ref('fact_transactions') }}
where transaction_sk is null
   or customer_sk is null
   or product_sk is null
   or country_sk is null
   or date_sk is null
   or quantity is null
   or price is null
   or line_amount is null
