-- Fails if any client's SCD2 validity ranges overlap
select a.client_id
from {{ ref('dim_client') }} a
join {{ ref('dim_client') }} b
  on a.client_id = b.client_id
 and a.onboarded_event_id < b.onboarded_event_id
 and a.valid_from < coalesce(b.valid_to, timestamp '9999-12-31 00:00:00')
 and b.valid_from < coalesce(a.valid_to, timestamp '9999-12-31 00:00:00')
