-- KPI 5: Activation rate (proxy)
-- Definition: share of onboarded clients that made at least one approved
--             purchase within their first 7 days ("activated"). Proxy for the
--             card-activation funnel until `card_issued` events exist.
-- Formula:    activated_clients / onboarded_clients
-- Grain:      one row per onboarding cohort day × segment
-- Source:     dim_client + fct_purchases
-- Rule:       cohort semantics — cohort = onboarding date, not calendar month;
--             ratio non-additive → keep counts.
with cohorts as (
    select
        cast(valid_from as date)    as cohort_date,
        client_id,
        segment
    from {{ ref('dim_client') }}
),
first_purchase as (
    select
        client_id,
        min(dt_event)               as first_purchase_date
    from {{ ref('fct_purchases') }}
    where status = 'approved'
    group by 1
)
select
    k.cohort_date                                   as date_key,
    k.segment,
    count(*)                                        as onboarded_clients,
    count(*) filter (
        where fp.first_purchase_date is not null
          and fp.first_purchase_date
              <= k.cohort_date + interval 7 day
    )                                               as activated_clients,
    count(*) filter (
        where fp.first_purchase_date is not null
          and fp.first_purchase_date
              <= k.cohort_date + interval 7 day
    ) * 1.0 / nullif(count(*), 0)                   as activation_rate
from cohorts k
left join first_purchase fp using (client_id)
group by 1, 2
