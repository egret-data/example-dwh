# Scenario: new-source-crm

fixture: trade
skills: dwh-start, dwh-requirement, dwh-model-design

## Prompt

We need data from our CRM system about customer visits. Please add it to the warehouse.

## Pass if

- Classifies as model-extending (new source, process, likely atomic metric).
- Asks for or drafts the requirement (process, grain, dimensions, metrics, source meta) as a `docs/designs/` record.
- Says it will stop for design approval (`design-approved`) before SQL.

## Fail if

- Writes or proposes dbt SQL or a DAG before approval.
- Adds YAML without a design record.
