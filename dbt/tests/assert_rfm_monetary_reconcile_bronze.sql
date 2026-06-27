-- X3: RFM monetary must reconcile with bronze eligible revenue (dedup + noise + RFM rules)
with bronze as (
    select * from read_parquet(
        '{{ var("bronze_dir") }}/year_month=*/data.parquet',
        filename = false,
        hive_partitioning = false
    )
),
deduped as (
    select distinct * from bronze
),
cleaned as (
    select *, quantity * price as line_amount
    from deduped
    where is_cancellation = true or price is null or price > 0
),
eligible as (
    select coalesce(sum(line_amount), 0) as revenue
    from cleaned
    where customer_id != ''
      and is_cancellation = false
      and line_amount > 0
),
rfm as (
    select coalesce(sum(monetary), 0) as revenue
    from {{ ref('mart_rfm') }}
),
compared as (
    select
        e.revenue as bronze_revenue,
        r.revenue as rfm_revenue,
        abs(r.revenue - e.revenue) / nullif(e.revenue, 0) as diff_pct
    from eligible e, rfm r
)
select 1
from compared
where bronze_revenue > 0
  and diff_pct > 0.001
