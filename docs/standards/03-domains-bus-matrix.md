# 03 — Domains, processes and the bus matrix

Scope: how to divide data domains and business processes, build the bus matrix, and recognise a model-extending
change. The source of truth is `warehouse/domains.yml`, `processes.yml` and `bus_matrix.yml`.

## Rules

### STD-03-01 Divide domains (MUST)

Divide data domains by department, business process or functional module, and keep them extensible: a new process
should find a home without renaming the others. A domain name is one token, because it fills one segment of table
names.

Correct:

```yaml
# warehouse/domains.yml
domains:
  - name: trade
    description: Orders and payments.
    owner: trade-data-team
```

Incorrect:

```yaml
# warehouse/domains.yml
domains:
  - name: order_and_payment    # more than one token
    description: Orders and payments.
    owner: trade-data-team
```

Source: Alibaba divide-data-domains
Checked by: DWH-Y01

### STD-03-02 Declare each process (MUST)

Each business process names its domain, its fact type (`transaction`, `periodic_snapshot` or
`accumulating_snapshot`) and a one-sentence grain. The schema requires all three and the domain must exist in
`domains.yml`; the checker does not judge whether the grain sentence is right.

Correct:

```yaml
# warehouse/processes.yml
processes:
  - name: payment
    domain: trade
    description: A customer pays for an order.
    fact_type: transaction
    grain: One row per payment received.
```

Incorrect:

```yaml
processes:
  - name: payment
    domain: finance       # not declared in domains.yml
    description: Payments.
    # fact_type and grain are missing
```

Source: Kimball (fact table types) · Alibaba analyze-business-processes
Checked by: DWH-Y01, DWH-Y03

### STD-03-03 Bus-matrix rows (MUST)

Every process has a `bus_matrix.yml` row listing the conformed dimensions it uses, with a role name for each
role-playing use. Two uses of one dimension in the same process (order date and ship date) get two cells with
different roles. A DWD of a process without a row is an error.

Correct:

```yaml
# warehouse/bus_matrix.yml
bus_matrix:
  - process: order
    dimensions:
      - {dimension: date, role: order_date}
      - {dimension: customer}
```

Incorrect:

```yaml
# warehouse/bus_matrix.yml: no row for process 'order'; a cell names a dimension that does not exist
bus_matrix:
  - process: payment
    dimensions:
      - {dimension: buyer}
```

Source: Kimball (enterprise bus matrix) · Alibaba define-dimensions-and-build-a-bus-matrix
Checked by: DWH-Y03, DWH-B03

### STD-03-04 DWD maps to a process (MUST)

Every DWD sets `config.meta.process`. Its `_key` columns are dimensions, or roles, of that process's bus-matrix row:
a key column `order_date_key` needs the role `order_date` (or the dimension `order_date`) in the row.

Correct:

```yaml
models:
  - name: dwd_trade_order_di
    config:
      meta: {process: order}
    columns:
      - name: order_date_key     # role of dimension date in the bus-matrix row
      - name: customer_key
```

Incorrect:

```yaml
models:
  - name: dwd_trade_order_di
    columns:
      - name: store_key          # no meta.process, and 'store' is not in the row
```

Source: Spec §8.1
Checked by: DWH-B01, DWH-B04

### STD-03-05 Model-extending changes need approval (MUST)

A PR that adds a domain, process, conformed dimension or atomic metric links a record in `docs/designs/` and carries
the `design-approved` label. The check compares the warehouse YAML with the base branch and looks for the label and
for a repo-relative link to an existing design record; a GitHub URL is not accepted.

Correct:

```text
PR description:
Adds dimension `customer` (trade).
Design: docs/designs/2026-11-04-date-dimension.md
Labels: design-approved
```

Incorrect:

```text
PR description:
Adds dimension `customer` (trade). Design is in the wiki.
# no docs/designs/ link and no design-approved label
```

Source: Spec §6.3
Checked by: DWH-G01, DWH-G02
