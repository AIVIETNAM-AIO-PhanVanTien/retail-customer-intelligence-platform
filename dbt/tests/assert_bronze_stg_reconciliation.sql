-- S3 / X1: bronze → staging row drop must be explainable (dedup + noise filter only)
with bronze as (
    select * from read_parquet(
        '{{ var("bronze_dir") }}/year_month=*/data.parquet',
        filename = false,
        hive_partitioning = false
    )
),
bronze_metrics as (
    select count(*) as bronze_count from bronze
),
deduped as (
    select distinct * from bronze
),
dedup_metrics as (
    select count(*) as dedup_count from deduped
),
with_amount as (
    select *, quantity * price as line_amount from deduped
),
expected_stg as (
    select count(*) as expected_count
    from with_amount
    where is_cancellation = true or price is null or price > 0
),
actual_stg as (
    select count(*) as actual_count
    from {{ ref('stg_silver__transactions') }}
)
select 1
from bronze_metrics b, dedup_metrics d, expected_stg e, actual_stg a
where a.actual_count != e.expected_count
   or e.expected_count > b.bronze_count
   or d.dedup_count > b.bronze_count
