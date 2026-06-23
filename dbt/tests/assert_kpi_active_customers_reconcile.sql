-- KPI mart active_customers must reconcile (per year_month) with distinct valid-purchase
-- customers in source. Catches drift if the mart's filter/division logic changes.
with source_cust as (
    select
        year_month,
        count(distinct customer_id) as active_customers
    from {{ ref('int_transactions__prepared') }}
    where is_valid_purchase
    group by year_month
),
mart_cust as (
    select
        year_month,
        active_customers
    from {{ ref('mart_kpi_monthly') }}
)
select
    coalesce(s.year_month, m.year_month) as year_month,
    s.active_customers as source_customers,
    m.active_customers as mart_customers
from source_cust s
full outer join mart_cust m on s.year_month = m.year_month
where coalesce(s.active_customers, 0) <> coalesce(m.active_customers, 0)
