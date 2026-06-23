-- G1: dim_country entities = distinct country in staging
with stg_countries as (
    select count(distinct country) as country_count
    from {{ ref('stg_silver__transactions') }}
),
dim_countries as (
    select count(*) as country_count
    from {{ ref('dim_country') }}
)
select 1
from stg_countries s, dim_countries d
where s.country_count != d.country_count
