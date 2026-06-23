-- Calendar derived columns must stay within valid ranges (Python silver_transform conventions)
select
    invoice,
    stock_code,
    invoice_date,
    invoice_year,
    invoice_month,
    invoice_day,
    invoice_quarter,
    invoice_day_of_week,
    invoice_week
from {{ ref('stg_silver__transactions') }}
where invoice_month not between 1 and 12
   or invoice_day not between 1 and 31
   or invoice_quarter not between 1 and 4
   or invoice_day_of_week not between 0 and 6
   or invoice_week not between 1 and 53
