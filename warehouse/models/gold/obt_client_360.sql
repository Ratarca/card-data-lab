-- Gold OBT: one row per current client, ready for portfolio, dashboard, and ML use.
-- It intentionally combines descriptive client attributes with behavioral metrics.
with purchase_summary as (
    select
        client_id,
        count(*)                                            as authorization_attempts,
        count(*) filter (where status = 'approved')        as approved_attempts,
        count(*) filter (where status = 'declined')        as declined_attempts,
        coalesce(sum(amount) filter (where status = 'approved'), 0) as lifetime_tpv,
        avg(amount) filter (where status = 'approved')     as avg_approved_ticket,
        min(dt_event)                                      as first_purchase_date,
        max(dt_event)                                      as last_purchase_date,
        count(distinct dt_event)                            as active_days
    from {{ ref('fct_purchases') }}
    group by 1
)
select
    c.client_id,
    c.segment,
    c.age,
    c.income,
    c.valid_from                                            as client_since,
    c.is_current,
    coalesce(p.authorization_attempts, 0)                   as authorization_attempts,
    coalesce(p.approved_attempts, 0)                         as approved_attempts,
    coalesce(p.declined_attempts, 0)                         as declined_attempts,
    coalesce(p.approved_attempts, 0) * 1.0
        / nullif(coalesce(p.authorization_attempts, 0), 0)  as approval_rate,
    coalesce(p.lifetime_tpv, 0)                              as lifetime_tpv,
    p.avg_approved_ticket,
    p.first_purchase_date,
    p.last_purchase_date,
    coalesce(p.active_days, 0)                               as active_days,
    c.income * 0.30                                         as estimated_credit_capacity,
    coalesce(p.lifetime_tpv, 0) * 1.0
        / nullif(c.income * 0.30, 0)                        as lifetime_capacity_utilization
from {{ ref('dim_client') }} c
left join purchase_summary p using (client_id)
where c.is_current
