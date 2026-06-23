-- G1: dim_product entities = distinct stock_code in staging
with stg_products as (
    select count(distinct stock_code) as product_count
    from {{ ref('stg_silver__transactions') }}
),
dim_products as (
    select count(*) as product_count
    from {{ ref('dim_product') }}
)
select 1
from stg_products s, dim_products d
where s.product_count != d.product_count
