{#
  prod: layer schema as-is (ods, dim, dwd, dws, ads).
  other targets: <target.schema>_<layer>, e.g. dev_viet_ods, ci_pr_12_ods.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {%- if custom_schema_name is none -%}
    {{ target.schema }}
  {%- elif target.name == 'prod' -%}
    {{ custom_schema_name | trim }}
  {%- else -%}
    {{ target.schema }}_{{ custom_schema_name | trim }}
  {%- endif -%}
{%- endmacro %}
