-- X3: RFM monetary total must reconcile with valid-purchase staging revenue
with eligible as (
    select coalesce(sum(line_amount), 0) as revenue
    from {{ ref('int_transactions__prepared') }}
    where is_valid_purchase
),
rfm as (
    select coalesce(sum(monetary), 0) as revenue
    from {{ ref('mart_rfm') }}
),
compared as (
    select
        e.revenue as stg_revenue,
        r.revenue as rfm_revenue,
        abs(r.revenue - e.revenue) / nullif(e.revenue, 0) as diff_pct
    from eligible e, rfm r
)
select 1
from compared
where stg_revenue > 0
  and diff_pct > 0.001
