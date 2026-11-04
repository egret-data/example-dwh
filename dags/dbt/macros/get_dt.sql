{#
  The partition date being processed, as 'YYYY-MM-DD': the Asia/Ho_Chi_Minh business day (spec D12).
  Airflow passes --vars '{dt: ...}' rendered from _common.dates.DT_TEMPLATE.
  Default, for manual dev runs: yesterday in Asia/Ho_Chi_Minh.
  Validated only at execution time, because `dbt ls`/parse render with placeholder values.
#}
{% macro get_dt() -%}
  {%- set today_vn = modules.datetime.datetime.now(modules.pytz.timezone('Asia/Ho_Chi_Minh')).date() -%}
  {%- set default_dt = (today_vn - modules.datetime.timedelta(days=1)).isoformat() -%}
  {%- set dt = var('dt', default_dt) | string -%}
  {%- if execute -%}
    {%- do modules.datetime.date.fromisoformat(dt) -%}
  {%- endif -%}
  {{- return(dt) -}}
{%- endmacro %}
