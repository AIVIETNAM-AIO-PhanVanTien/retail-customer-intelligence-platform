-- year_month partition key must match invoice_date (YYYY-MM)
select
    invoice,
    stock_code,
    invoice_date,
    year_month
from {{ ref('stg_silver__transactions') }}
where year_month != strftime(cast(invoice_date as date), '%Y-%m')
