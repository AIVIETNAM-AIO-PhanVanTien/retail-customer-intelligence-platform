-- X3: segment distribution must sum to mart_rfm rows (= valid-purchase customer base)
with mart as (
    select count(*) as mart_rows
    from {{ ref('mart_rfm') }}
),
segment_sum as (
    select coalesce(sum(segment_count), 0) as segment_total
    from (
        select count(*) as segment_count
        from {{ ref('mart_rfm') }}
        group by segment
    )
),
eligible as (
    select count(distinct customer_id) as eligible_count
    from {{ ref('int_transactions__prepared') }}
    where is_valid_purchase
)
select 1
from mart m, segment_sum s, eligible e
where m.mart_rows != s.segment_total
   or m.mart_rows != e.eligible_count
   or exists (
       select 1
       from {{ ref('mart_rfm') }}
       where segment is null
   )
