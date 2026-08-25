-- Grain: 1 row = 1 authorization decision (subset of purchase attempts)
select
    event_id,
    client_id,
    ts_event,
    dt_event,
    channel,
    merchant,
    amount
from {{ ref('stg_purchase_events') }}
where status = 'approved'
