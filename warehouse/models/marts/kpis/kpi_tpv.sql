-- KPI 2: TPV (Total Purchase Volume)
-- Definition: sum of approved purchase amounts.
-- Formula:    Σ amount where status = 'approved'
-- Grain:      one row per day × channel
-- Source:     fct_purchases (atomic fact)
-- Rule:       amount is fully additive → safe to sum across any dimension.
select
    dt_event                            as date_key,
    channel,
    count(*)                            as tx_count,
    sum(amount)                         as tpv,
    avg(amount)                         as avg_ticket
from {{ ref('fct_purchases') }}
where status = 'approved'
group by 1, 2
