-- dim_client: SCD2 dimension built from onboarding events.
-- In this lab each client has exactly one onboarded event, so validity is
-- [onboarded_at, ∞). The SCD2 structure (valid_from/valid_to/is_current) is
-- already in place so future client-attribute events can be appended without
-- changing the model.
select
    client_id,
    event_id as onboarded_event_id,
    ts_event as valid_from,
    cast(null as timestamp) as valid_to,
    true as is_current,
    segment,
    age,
    income
from {{ ref('stg_onboarding_events') }}
