-- G3 / G4: mart_rfm customers must be a subset of dim known customers
select m.customer_id
from {{ ref('mart_rfm') }} m
left join {{ ref('dim_customer') }} d
    on m.customer_id = d.customer_id
where d.customer_id is null
