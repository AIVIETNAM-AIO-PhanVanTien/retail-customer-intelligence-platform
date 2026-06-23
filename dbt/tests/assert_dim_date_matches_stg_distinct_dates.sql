-- G1: dim_date rows = distinct invoice dates in staging
with stg_dates as (
    select count(distinct cast(invoice_date as date)) as date_count
    from {{ ref('stg_silver__transactions') }}
),
dim_dates as (
    select count(*) as date_count
    from {{ ref('dim_date') }}
)
select 1
from stg_dates s, dim_dates d
where s.date_count != d.date_count
