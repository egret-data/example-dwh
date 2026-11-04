---
name: dwh-model-design
description: Use when a design record exists or a reuse change is agreed, and warehouse/*.yml and the table specifications must be updated before any SQL is written
---

# dwh-model-design: design in YAML, then stop

## Steps

1. **Update the warehouse YAML**, reusing names, in this order:
   1. `glossary.yml`
   2. `domains.yml`
   3. `processes.yml`
   4. `dimensions.yml` (history type; historical or current attributes)
   5. `bus_matrix.yml` (roles)
   6. `modifiers.yml`
   7. `metrics.yml` (names follow `{modifiers}_{atomic}_{agg}_{period}`)
2. **Validate.** Run `make validate` until it reports `0 finding(s)`.
3. **Specify every table** in the design record or the PR description:
   - layer and name;
   - a one-sentence grain;
   - keys, columns, upstream models;
   - load (partition replacement or merge);
   - history (an SCD4 `_hist` snapshot);
   - partition `dt`.
4. **Dry-run each name.** Run `uv run --project tools/dwh dwh scaffold <model> --from ... --grain ... [--metric ...]`
   without `--write`. A naming or design error shows up here.
5. **Model-extending change: STOP.**
   1. Commit the design record and the YAML on a branch.
   2. Open a PR that links `docs/designs/<record>.md`.
   3. Ask a data architect to review it and add the `design-approved` label.
   4. Write no SQL until the label is on the PR.
6. **Reuse change:** put the table specification in the PR description and continue with `dwh-implement`.

## Red flags

| Thought | Reality |
|---------|---------|
| "I'll write the SQL while waiting for approval" | If the design changes in review, the SQL is wasted. Wait. |
| "Make every attribute historical, to be safe" | Each historical attribute costs a point-in-time join. Mark it historical only if facts need the value at event time. |
| "Add a DWS so BI is fast" | Build a DWS only with two or more consumers or measured performance evidence (`07-dws-ads.md`). |
| "Put 1d and 7d metrics in one DWS" | One period per DWS table. |

## Rules

`docs/standards/02-naming.md`, `03-domains-bus-matrix.md`, `04-dimensions.md`, `05-facts.md`, `06-metrics.md`,
`07-dws-ads.md`.
