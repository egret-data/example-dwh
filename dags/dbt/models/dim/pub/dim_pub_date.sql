{{ config(materialized='table') }}

-- One row per calendar day (spec D11); the durable key is a hash of the date.
-- The unknown ('-1') and not applicable ('-2') members have a null date (STD-04-06).
with current_members as (
    select
        {{ dbt_utils.generate_surrogate_key(['cal_date']) }} as date_key,
        t.cal_date,
        year(cal_date)                                       as year,
        month(cal_date)                                      as month,
        day_of_week(cal_date)                                as weekday
    from unnest(sequence(date '2020-01-01', date '2030-12-31', interval '1' day)) as t (cal_date)
),

special_members as (
    select
        '-1'                 as date_key,
        cast(null as date)   as cal_date,
        cast(null as bigint) as year,
        cast(null as bigint) as month,
        cast(null as bigint) as weekday
    union all
    select
        '-2'                 as date_key,
        cast(null as date)   as cal_date,
        cast(null as bigint) as year,
        cast(null as bigint) as month,
        cast(null as bigint) as weekday
)

select
    date_key,
    cal_date,
    year,
    month,
    weekday
from current_members
union all
select
    date_key,
    cal_date,
    year,
    month,
    weekday
from special_members
