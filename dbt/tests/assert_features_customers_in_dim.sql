-- mart_features customers must exist in dim_customer (known customers only).
select m.customer_id
from {{ ref('mart_features') }} m
left join {{ ref('dim_customer') }} d
    on m.customer_id = d.customer_id
where d.customer_id is null
