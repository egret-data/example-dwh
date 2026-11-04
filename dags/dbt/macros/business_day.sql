{#
  Spec D12: `dt` is the Asia/Ho_Chi_Minh calendar day.
  source_ts() turns a naive source timestamp into timestamp(6) with time zone, read in the source's
  timezone. in_business_day() keeps rows whose instant falls in [dt 00:00, dt+1 00:00)
  Asia/Ho_Chi_Minh, comparing the raw source column so the filter is pushed down to the source. Asia/Ho_Chi_Minh has no DST, so "+ interval '1' day" is exactly 24 hours.
#}
{% macro business_tz() -%}
  {{- return('Asia/Ho_Chi_Minh') -}}
{%- endmacro %}

{% macro source_ts(column, source_tz) -%}
with_timezone(cast({{ column }} as timestamp(6)), '{{ source_tz }}')
{%- endmacro %}

{% macro in_business_day(column, source_tz) -%}
{#- The source column stays raw and is compared with constants converted into the source zone, so
    Trino pushes the window down to the source database instead of scanning the whole table. -#}
{%- set day_start = "with_timezone(timestamp '" ~ get_dt() ~ " 00:00:00', '" ~ business_tz() ~ "')" -%}
{%- set raw = "cast(" ~ column ~ " as timestamp(6))" -%}
{{ raw }} >= cast({{ day_start }} at time zone '{{ source_tz }}' as timestamp(6))
    and {{ raw }} < cast(({{ day_start }} + interval '1' day) at time zone '{{ source_tz }}' as timestamp(6))
{%- endmacro %}
