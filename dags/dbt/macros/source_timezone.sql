{#
  IANA timezone of a source table's naive timestamps, from the source's `config.meta.timezone`
  (dbt merges source-level meta into each table's meta). dbt unit tests have no graph.sources, so
  every unit test overrides this macro.
#}
{% macro source_timezone(source_name, table_name) -%}
  {%- if not execute -%}
    {{- return('UTC') -}}
  {%- endif -%}
  {%- for node in graph.sources.values() -%}
    {%- if node.source_name == source_name and node.name == table_name -%}
      {%- set tz = node.meta.get('timezone') -%}
      {%- if not tz -%}
        {{- exceptions.raise_compiler_error('source ' ~ source_name ~ '.' ~ table_name ~ ' has no meta.timezone') -}}
      {%- endif -%}
      {{- return(tz) -}}
    {%- endif -%}
  {%- endfor -%}
  {{- exceptions.raise_compiler_error('unknown source ' ~ source_name ~ '.' ~ table_name) -}}
{%- endmacro %}
