-- Feature value ranges aligned with ml/validation.py (BINARY, NON_NEGATIVE,
-- UNIT_INTERVAL, CLIPPED_MAX) plus base-customer rules frequency >= 1, monetary > 0.
select
    customer_id
from {{ ref('mart_features') }}
where is_one_time_buyer not in (0, 1)
   or is_uk not in (0, 1)
   or frequency < 1
   or monetary <= 0
   or recency_days < 0
   or frequency_last_30d < 0
   or frequency_last_90d < 0
   or monetary_last_90d < 0
   or avg_order_value < 0
   or avg_basket_size < 0
   or avg_unit_price < 0
   or total_quantity < 0
   or unique_products < 0
   or tenure_days < 0
   or avg_days_between_orders < 0
   or std_days_between_orders < 0
   or days_since_first_purchase < 0
   or max_single_order_value < 0
   or min_single_order_value < 0
   or recency_one_time < 0
   or cancellation_rate < 0
   or cancellation_rate > 1
   or return_quantity_rate < 0
   or return_quantity_rate > 1
   or weekend_purchase_ratio < 0
   or weekend_purchase_ratio > 1
   or ratio_frequency_90d < 0
   or ratio_frequency_90d > 1
   or velocity_ratio_180d < 0
   or velocity_ratio_180d > 1
   or spending_recency_ratio < 0
   or spending_recency_ratio > 1
   or velocity_ratio_30d_90d < 0
   or velocity_ratio_30d_90d > 1
   or product_diversity_trend < 0
   or product_diversity_trend > 1
   or overdue_ratio < 0
   or overdue_ratio > 10
   or purchase_regularity < 0
   or purchase_regularity > 5
   or monetary_acceleration < 0
   or monetary_acceleration > 20
