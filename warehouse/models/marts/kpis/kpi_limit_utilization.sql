-- KPI 4: Limit utilization (proxy)
-- Definition: average spend per active client per day vs. estimated credit
--             capacity. Until `limit_assigned` events exist in the lake we use
--             income-based capacity: lab rule of thumb = 30% of monthly income.
-- Formula:    daily_spend_per_client / (income * 0.30 / 30)
-- Grain:      one row per day × segment
-- Source:     fct_purchases + dim_client
-- Rule:       utilization > 1.0 signals stress; ratio non-additive → keep
--             numerator/denominator columns.
select
    f.dt_event                                    as date_key,
    c.segment                                     as segment,
    count(distinct f.client_id)                   as active_clients,
    sum(f.amount)                                 as spend,
    sum(i.income * 0.30 / 30.0)                   as capacity,
    sum(f.amount) * 1.0 / nullif(sum(i.income * 0.30 / 30.0), 0) as limit_utilization
from {{ ref('fct_purchases') }} f
join {{ ref('dim_client') }} c
  on c.client_id = f.client_id and c.is_current
join {{ ref('dim_client') }} i
  on i.client_id = f.client_id and i.is_current
where f.status = 'approved'
group by 1, 2
