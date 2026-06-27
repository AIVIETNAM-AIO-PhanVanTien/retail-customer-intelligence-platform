-- X5 / B2: per-partition Bronze → staging row counts must match cleaning rules
with bronze as (
    select
        *,
        strftime(invoice_date, '%Y-%m') as year_month
    from read_parquet(
        '{{ var("bronze_dir") }}/year_month=*/data.parquet',
        filename = false,
        hive_partitioning = false
    )
),
deduped as (
    select distinct * from bronze
),
with_amount as (
    select *, quantity * price as line_amount from deduped
),
expected as (
    select
        year_month,
        count(*) as expected_count
    from with_amount
    where is_cancellation = true or price is null or price > 0
    group by year_month
),
actual as (
    select
        year_month,
        count(*) as actual_count
    from {{ ref('stg_silver__transactions') }}
    group by year_month
)
select
    coalesce(e.year_month, a.year_month) as year_month,
    e.expected_count,
    a.actual_count
from expected e
full outer join actual a on e.year_month = a.year_month
where coalesce(e.expected_count, 0) != coalesce(a.actual_count, 0)
