-- Feature sanity bounds (base customers are valid-purchase customers):
--   recency_days >= 0, frequency >= 1, monetary > 0, avg_order_value >= 0.
-- Catches broken aggregation / fill / clip logic.
select
    customer_id,
    recency_days,
    frequency,
    monetary,
    avg_order_value
from {{ ref('mart_features') }}
where recency_days < 0
   or frequency < 1
   or monetary <= 0
   or avg_order_value < 0
