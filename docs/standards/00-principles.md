# 00 — Principles

Scope: how every change to the warehouse starts and what "done" means. The rules apply to all layers (ODS, DIM, DWD,
DWS, ADS) and to every contributor, human or agent.

## Rules

### STD-00-01 Start from a business process (MUST)

Model the business process that produces the facts, not the layout of a report. A report is served from the model
built for the process. If two reports need the same events, they share one process and one DWD model. The limit: this
rule is a design habit, no tool checks it.

Correct:

```yaml
# warehouse/processes.yml: the process is the unit of design
processes:
  - name: order
    domain: trade
    description: A customer places an order.
    fact_type: transaction
    grain: One row per order line placed.
```

Incorrect:

```yaml
# warehouse/processes.yml: named after a report, not after what happens in the business
processes:
  - name: weekly_sales_report
    domain: trade
    description: Numbers for the Monday sales meeting.
    fact_type: periodic_snapshot
    grain: One row per report line.
```

Source: Kimball (The Data Warehouse Toolkit, 3rd ed., four-step design) · Alibaba analyze-business-processes

### STD-00-02 Declare the grain first (MUST)

Write one sentence "one row per ..." before choosing columns. Every model's grain test encodes that sentence: a
`unique` test, or `dbt_utils.unique_combination_of_columns`, over the grain columns, and those columns are `not_null`.
The checker finds the test and the `not_null` tests; it cannot read the sentence, so the reviewer compares the two.

Correct:

```yaml
models:
  - name: dwd_trade_order_di
    description: One row per order line placed.
    data_tests:
      - dbt_utils.unique_combination_of_columns:
          arguments:
            combination_of_columns: [order_id, order_line_id]
    columns:
      - name: order_id
        data_tests: [not_null]
      - name: order_line_id
        data_tests: [not_null]
```

Incorrect:

```yaml
models:
  - name: dwd_trade_order_di
    description: Orders.
    # no grain sentence and no uniqueness test: the grain is unknown
    columns:
      - name: order_id
```

Source: Kimball (four-step design) · Alibaba data-warehouse-detail-layer
Checked by: DWH-T01, DWH-T02

### STD-00-03 Reuse before create (MUST)

Search `warehouse/*.yml` (or the catalogue) for an existing process, dimension and metric before proposing one. Adding
a domain, process, dimension or atomic metric is a model-extending change: it needs an approved design record in
`docs/designs/` and the `design-approved` label on the PR. The gate compares the warehouse YAML on the PR with the
base branch; it does not judge whether the design is good.

Correct:

```text
PR description:
Adds the process `payment` to the trade domain.
Design: docs/designs/2026-11-10-trade-payment.md
Labels: design-approved
```

Incorrect:

```text
PR description:
Adds the process `payment` to the trade domain.
# no link to a design record and no design-approved label
```

Source: Alibaba overall-process · Spec §6.3
Checked by: DWH-G01, DWH-G02

### STD-00-04 One definition per metric (MUST)

A metric is defined once in `warehouse/metrics.yml` and referenced by name everywhere else: in DWS, ADS, BI and
documentation. A second definition under the same name is an error, and a metric column in DWS or ADS carries the
metric's name through `meta.metric`. Computing the same number with a private formula in another model creates two
answers to one question.

Correct:

```yaml
# warehouse/metrics.yml
atomic:
  - name: pay_amt
    description: Amount of one payment.
    process: payment
    additivity: additive
    aggregation: sum
```

Incorrect:

```yaml
# warehouse/metrics.yml: the same name is defined twice
atomic:
  - name: pay_amt
    process: payment
  - name: pay_amt
    process: refund
```

Source: Alibaba specify-statistical-metrics
Checked by: DWH-Y02, DWH-M04

### STD-00-05 Conformed dimensions (MUST)

A dimension used by more than one process is declared once in `warehouse/dimensions.yml` and shared. Facts reference
it by name in `bus_matrix.yml`; they do not redefine it. The checker verifies that every dimension a bus-matrix row
names exists in `dimensions.yml`.

Correct:

```yaml
# warehouse/bus_matrix.yml: both processes use the one date dimension
bus_matrix:
  - process: order
    dimensions:
      - {dimension: date, role: order_date}
  - process: payment
    dimensions:
      - {dimension: date, role: pay_date}
```

Incorrect:

```yaml
# warehouse/bus_matrix.yml: a second, private date dimension for payments
bus_matrix:
  - process: payment
    dimensions:
      - {dimension: payment_calendar}
```

Source: Kimball (conformed dimensions) · Alibaba define-dimensions-and-build-a-bus-matrix
Checked by: DWH-Y03

### STD-00-06 Evidence before done (MUST)

A change is done only with real command output: build, lint, row counts and reconciliation (skill `dwh-verify`). The
PR description pastes or links that output. "It should work" and "tests pass" without output are not evidence.

Correct:

```text
$ dbt build --select +dwd_trade_order_di
Done. PASS=14 WARN=0 ERROR=0 SKIP=0 TOTAL=14
$ uv run --locked --project tools/dwh dwh lint
0 finding(s)
```

Incorrect:

```text
Built and linted locally, everything is green.
# no command, no output
```

Source: Spec §6.2
