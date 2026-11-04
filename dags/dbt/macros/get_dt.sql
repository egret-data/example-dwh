{#
  The partition date being processed, as 'YYYY-MM-DD'.
  Airflow passes --vars '{dt: <ds>}'. Default: yesterday (for manual dev runs).
  Validated only at execution time, because `dbt ls`/parse render with placeholder values.
#}
{% macro get_dt() -%}
  {%- set default_dt = (modules.datetime.date.today() - modules.datetime.timedelta(days=1)).isoformat() -%}
  {%- set dt = var('dt', default_dt) | string -%}
  {%- if execute -%}
    {%- do modules.datetime.date.fromisoformat(dt) -%}
  {%- endif -%}
  {{- return(dt) -}}
{%- endmacro %}
