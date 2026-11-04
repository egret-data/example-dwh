{#
  Iceberg maintenance (STD-08-08, STD-08-09). Run weekly by the iceberg_maintenance DAG:
    dbt run-operation iceberg_maintenance --args '{dry_run: false}'
  For every dt-partitioned model of the ODS, DWD, DWS and ADS layers (DIM and snapshots are kept forever):
  1. delete the dt partitions older than config.meta.retention_days, or the layer default;
  2. optimize (compact small files), expire_snapshots and remove_orphan_files (7 days).
  Every statement is logged. dry_run=true (the default) logs them and runs none.
  The var maintenance_today ('YYYY-MM-DD') overrides today, for tests.
#}
{% macro iceberg_maintenance(dry_run=true) %}
  {%- set default_days = {'ods': 400, 'dwd': 1095, 'dws': 1095, 'ads': 400} -%}
  {%- set today = var('maintenance_today', modules.datetime.datetime.now(modules.pytz.timezone(business_tz())).date().isoformat()) -%}
  {%- for node in graph.nodes.values() if node.resource_type == 'model' -%}
    {%- set layer = node.fqn[1] -%}
    {%- set partitioning = (node.config.properties or {}).get('partitioning', '') -%}
    {%- if layer in default_days and 'dt' in partitioning -%}
      {%- set relation = adapter.get_relation(database=node.database, schema=node.schema, identifier=node.alias) -%}
      {%- if relation is none -%}
        {{ log('maintenance skip (not built): ' ~ node.unique_id, info=true) }}
      {%- else -%}
        {%- set days = (node.config.meta or {}).get('retention_days', default_days[layer]) | int -%}
        {%- set statements = [
          "delete from " ~ relation ~ " where dt < date_add('day', -" ~ days ~ ", date '" ~ today ~ "')",
          "alter table " ~ relation ~ " execute optimize",
          "alter table " ~ relation ~ " execute expire_snapshots(retention_threshold => '7d')",
          "alter table " ~ relation ~ " execute remove_orphan_files(retention_threshold => '7d')"
        ] -%}
        {%- for statement in statements -%}
          {{ log(('[dry run] ' if dry_run else '') ~ statement, info=true) }}
          {%- if not dry_run -%}
            {%- do run_query(statement) -%}
          {%- endif -%}
        {%- endfor -%}
      {%- endif -%}
    {%- endif -%}
  {%- endfor -%}
{% endmacro %}
