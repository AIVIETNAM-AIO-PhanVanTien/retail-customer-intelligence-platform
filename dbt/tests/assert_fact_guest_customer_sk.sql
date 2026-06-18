-- P1: guest transactions (empty customer_id) must map to customer_sk = 0
with guest_stg as (
    select count(*) as guest_count
    from {{ ref('stg_silver__transactions') }}
    where customer_id = ''
),
guest_fact as (
    select count(*) as guest_count
    from {{ ref('fact_transactions') }}
    where customer_sk = 0
)
select
    s.guest_count as stg_guest_count,
    f.guest_count as fact_guest_count
from guest_stg s, guest_fact f
where s.guest_count != f.guest_count
