-- dim_date: one row per calendar day covering the lake's date range
with dates as (
    select distinct dt_event
    from {{ ref('stg_purchase_events') }}
    union
    select distinct dt_event
    from {{ ref('stg_onboarding_events') }}
)
select
    cast(dt_event as date)                          as date_key,   -- YYYY-MM-DD
    cast(dt_event as date)                          as date_day,
    extract(year  from dt_event)::integer           as year,
    extract(quarter from dt_event)::integer         as quarter,
    extract(month from dt_event)::integer           as month,
    strftime(dt_event, '%B')                        as month_name,
    extract(week from dt_event)::integer            as week_of_year,
    extract(dow from dt_event)::integer             as day_of_week,
    strftime(dt_event, '%A')                        as day_name,
    case when extract(dow from dt_event) in (0, 6) then true else false end as is_weekend
from dates
order by date_key
