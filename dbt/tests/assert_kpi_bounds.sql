-- KPI mart bounds: non-negative counts/revenue, positive line_count,
-- rates in [0, 1] when defined. aov and cancellation_order_rate may be null
-- when the denominator is zero.
select
    year_month
from {{ ref('mart_kpi_monthly') }}
where revenue < 0
   or units_sold < 0
   or orders < 0
   or active_customers < 0
   or cancelled_orders < 0
   or line_count <= 0
   or (aov is not null and aov < 0)
   or (
       cancellation_order_rate is not null
       and (cancellation_order_rate < 0 or cancellation_order_rate > 1)
   )
