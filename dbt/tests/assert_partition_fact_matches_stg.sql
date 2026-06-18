-- X5: per-partition fact = full staging rows
with stg_by_month as (
    select
        year_month,
        count(*) as stg_count
    from {{ ref('stg_silver__transactions') }}
    group by year_month
),
fact_by_month as (
    select
        strftime(d.date, '%Y-%m') as year_month,
        count(*) as fact_count
    from {{ ref('fact_transactions') }} f
    inner join {{ ref('dim_date') }} d on f.date_sk = d.date_sk
    group by 1
)
select
    coalesce(s.year_month, f.year_month) as year_month,
    s.stg_count,
    f.fact_count
from stg_by_month s
full outer join fact_by_month f on s.year_month = f.year_month
where coalesce(s.stg_count, 0) != coalesce(f.fact_count, 0)
