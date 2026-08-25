-- Grain: 1 row = 1 purchase attempt (approved or declined)
select
    event_id,
    client_id,
    ts_event,
    dt_event,
    status,
    decline_reason,
    channel,
    merchant,
    amount
from {{ ref('stg_purchase_events') }}
