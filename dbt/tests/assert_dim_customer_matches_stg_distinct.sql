-- G1: dim_customer known entities = distinct non-empty customer_id in staging
with stg_customers as (
    select count(distinct customer_id) as customer_count
    from {{ ref('stg_silver__transactions') }}
    where customer_id != ''
),
dim_known as (
    select count(*) as customer_count
    from {{ ref('dim_customer') }}
    where customer_id != ''
)
select 1
from stg_customers s, dim_known d
where s.customer_count != d.customer_count
