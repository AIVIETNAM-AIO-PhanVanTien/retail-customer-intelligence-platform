-- KPI mart revenue must reconcile (per year_month) with valid-purchase revenue in source.
with source_rev as (
    select
        year_month,
        sum(line_amount) as revenue
    from {{ ref('int_transactions__prepared') }}
    where is_valid_purchase
    group by year_month
),
mart_rev as (
    select
        year_month,
        revenue
    from {{ ref('mart_kpi_monthly') }}
)
select
    coalesce(s.year_month, m.year_month) as year_month,
    s.revenue as source_revenue,
    m.revenue as mart_revenue
from source_rev s
full outer join mart_rev m on s.year_month = m.year_month
where coalesce(s.revenue, 0) <> coalesce(m.revenue, 0)
