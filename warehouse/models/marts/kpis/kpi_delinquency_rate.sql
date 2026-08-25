-- KPI 3: Delinquency rate (proxy)
-- Definition: share of declined attempts caused by limit_exceeded — a proxy for
--             financial stress until invoice/payment events exist in the lake.
-- Formula:    limit_exceeded_declines / total_declines
-- Grain:      one row per day × decline_reason
-- Source:     fct_purchases (atomic fact)
-- Rule:       numerator ⊆ denominator; ratio non-additive → keep counts.
select
    dt_event                                        as date_key,
    decline_reason,
    count(*)                                        as declines,
    count(*) filter (where decline_reason = 'limit_exceeded') as limit_exceeded_declines,
    count(*) filter (where decline_reason = 'limit_exceeded') * 1.0
        / nullif(count(*), 0)                       as delinquency_rate_proxy
from {{ ref('fct_purchases') }}
where status = 'declined'
group by 1, 2
