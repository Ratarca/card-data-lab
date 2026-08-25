-- One row per purchase event (authorized or declined)
-- aggregate_id = client_id (the client is the business actor); card_id rides in the payload.
select
    event_id,
    ts_event,
    dt_event,
    aggregate_id as client_id,
    coalesce(json_extract_string(payload, '$.card_id'), '') as card_id,
    schema_version,
    case
        when event_type = 'purchase.authorized' then 'approved'
        when event_type = 'purchase.declined'   then 'declined'
        else 'unknown'
    end                                             as status,
    coalesce(json_extract_string(payload, '$.decline_reason'), 'none') as decline_reason,
    json_extract_string(payload, '$.channel')       as channel,
    json_extract_string(payload, '$.merchant')      as merchant,
    json_extract(payload, '$.amount')::decimal(12,2) as amount
from {{ source('lake', 'raw_events') }}
where event_type in ('purchase.authorized', 'purchase.declined')
