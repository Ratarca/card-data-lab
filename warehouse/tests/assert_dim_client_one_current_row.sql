-- Fails if any client has more than one current row (SCD2 invariant)
select client_id
from {{ ref('dim_client') }}
group by client_id
having sum(case when is_current then 1 else 0 end) <> 1
