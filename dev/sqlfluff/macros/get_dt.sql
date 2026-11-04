{# sqlfluff only: dbt's `modules` is unavailable under the jinja templater, so dt is a fixed date. #}
{% macro get_dt() %}{{ return('2026-11-02') }}{% endmacro %}
