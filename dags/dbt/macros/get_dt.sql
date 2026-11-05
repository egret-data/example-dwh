{#
  The partition date being processed, as 'YYYY-MM-DD': the Asia/Ho_Chi_Minh business day (spec D12).
  Airflow passes --vars '{dt: ...}' rendered from _common.dates.DT_TEMPLATE or ASSET_DT_TEMPLATE.
  Default, for manual dev runs: yesterday in Asia/Ho_Chi_Minh.
  Validated only at execution time, because `dbt ls`/parse render with placeholder values.
  ASSET_DT_TEMPLATE renders 'MULTIPLE:<day>,<day>' when one asset-triggered run collapses several business days
  (STD-11-03): the run fails here, naming the days to rerun.
#}
{% macro get_dt() -%}
  {%- set today_vn = modules.datetime.datetime.now(modules.pytz.timezone('Asia/Ho_Chi_Minh')).date() -%}
  {%- set default_dt = (today_vn - modules.datetime.timedelta(days=1)).isoformat() -%}
  {%- set dt = var('dt', default_dt) | string -%}
  {%- if execute -%}
    {%- if dt.startswith('MULTIPLE:') -%}
      {%- do exceptions.raise_compiler_error(
        "dt " ~ dt ~ ": this asset-triggered run collapsed several business days into one, and one run builds"
        ~ " exactly one dt. Rerun the DAG by hand once per listed day with conf.dt, oldest first ("
        ~ dt[9:].replace(',', ', ') ~ "). See STD-11-03 and the dwh-backfill skill."
      ) -%}
    {%- endif -%}
    {%- do modules.datetime.date.fromisoformat(dt) -%}
  {%- endif -%}
  {{- return(dt) -}}
{%- endmacro %}
