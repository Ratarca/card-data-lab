-- KPI 4: Limit utilization (proxy)
-- Definition: monthly credit-limit stock, used balance, and available balance.
-- Until `limit.assigned` events arrive in the lake, the client limit proxy is
-- 30% of monthly income. Approved purchases consume that stock cumulatively
-- inside each calendar month; the balance resets at the next month boundary.
-- Grain:      one row per calendar day × segment
-- Rule:       `used_limit` is month-to-date spend, not daily TPV. Keep the
--             numerator and denominator because the utilization ratio is
--             non-additive. `over_limit_amount` exposes simulator stress.
with calendar as (
    select date_key
    from {{ ref('dim_date') }}
),
client_limits as (
    select
        client_id,
        segment,
        cast(valid_from as date) as onboarded_date,
        income * 0.30            as credit_limit_proxy
    from {{ ref('dim_client') }}
    where is_current
),
daily_client_spend as (
    select
        d.date_key,
        c.segment,
        c.client_id,
        c.credit_limit_proxy,
        coalesce(sum(f.amount), 0) as daily_spend
    from calendar d
    join client_limits c
      on c.onboarded_date <= d.date_key
    left join {{ ref('fct_purchases') }} f
      on f.client_id = c.client_id
     and f.dt_event = d.date_key
     and f.status = 'approved'
    group by 1, 2, 3, 4
),
client_daily_balance as (
    select
        *,
        sum(daily_spend) over (
            partition by client_id, date_trunc('month', date_key)
            order by date_key
            rows between unbounded preceding and current row
        ) as used_limit
    from daily_client_spend
)
select
    date_key,
    segment,
    count(*)                                            as active_clients,
    sum(daily_spend)                                    as daily_spend,
    sum(credit_limit_proxy)                             as capacity,
    sum(least(used_limit, credit_limit_proxy))          as used_limit,
    sum(greatest(credit_limit_proxy - used_limit, 0))   as available_limit,
    sum(greatest(used_limit - credit_limit_proxy, 0))   as over_limit_amount,
    sum(used_limit) * 1.0 / nullif(sum(credit_limit_proxy), 0)
                                                        as limit_utilization
from client_daily_balance
group by 1, 2
