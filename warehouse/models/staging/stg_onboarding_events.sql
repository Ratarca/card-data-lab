-- One row per customer.onboarded event
select
    event_id,
    ts_event,
    dt_event,
    aggregate_id as client_id,
    schema_version,
    json_extract_string(header, '$.trace_id')      as trace_id,
    json_extract_string(header, '$.source_service') as source_service,
    json_extract_string(payload, '$.segment')       as segment,
    json_extract(payload, '$.age')::integer         as age,
    json_extract(payload, '$.income')::decimal(12,2) as income
from {{ source('lake', 'raw_events') }}
where event_type = 'customer.onboarded'
