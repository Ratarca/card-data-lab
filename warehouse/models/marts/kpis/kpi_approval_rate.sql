-- KPI 1: Approval rate
-- Definition: share of purchase attempts that were approved.
-- Formula:    approved_attempts / total_attempts
-- Grain:      one row per day × client segment
-- Source:     fct_purchases (atomic fact; numerator/denominator pattern —
--             store counts, compute the ratio in the model layer)
-- Rule:       ratio is non-additive → never sum approval_rate across rows;
--             re-aggregate from attempts/approved instead.
select
    dt_event                                as date_key,
    coalesce(c.segment, 'unknown')          as segment,
    count(*)                                as attempts,
    count(*) filter (where status = 'approved') as approved,
    count(*) filter (where status = 'approved') * 1.0
        / nullif(count(*), 0)               as approval_rate
from {{ ref('fct_purchases') }} f
left join {{ ref('dim_client') }} c
       on c.client_id = f.client_id and c.is_current
group by 1, 2
