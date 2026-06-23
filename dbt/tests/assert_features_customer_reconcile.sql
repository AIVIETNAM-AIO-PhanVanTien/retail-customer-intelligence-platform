-- mart_features must contain exactly the customers with >=1 valid purchase
-- in source (matches ml/features.py base grain).
with src_cust as (
    select count(distinct customer_id) as customer_count
    from {{ ref('int_transactions__prepared') }}
    where is_valid_purchase
),
mart_cust as (
    select count(*) as customer_count
    from {{ ref('mart_features') }}
)
select 1
from src_cust s, mart_cust m
where s.customer_count <> m.customer_count
