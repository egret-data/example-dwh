# 02 — Naming

Scope: table, column and metric names. Names carry the layer, the domain and the grain, so a reader can place a table
without opening it. The rules apply to all layers; the glossary rules apply outside ODS.

Differences from Alibaba:

- Alibaba's slot after `dim_` or `dwd_` holds the business segment. Here it holds `pub` or the domain (decision D10).
- The partition column is `dt` DATE, not Alibaba's `ds` STRING.
- The ODS and ADS name templates are this project's own; Alibaba has no ODS or ADS template.

## Rules

### STD-02-01 ODS names (MUST)

`ods_{source}_{table}_{di|df}`. The source segment equals the folder `models/ods/<source>/` and the `source()` the
model reads. `di` is a daily incremental load and `df` a daily full load.

Correct:

```text
models/ods/shop/ods_shop_orders_di.sql     # reads source('shop', 'orders')
```

Incorrect:

```text
models/ods/shop/ods_store_orders_di.sql    # source segment 'store' is not the folder 'shop'
```

Source: Spec §7
Checked by: DWH-N01, DWH-N02

### STD-02-02 DIM names (MUST)

`dim_pub_{dimension}` for a dimension shared across domains, `dim_{domain}_{dimension}` for one owned by a domain. The
second segment is `pub` or a domain declared in `warehouse/domains.yml`.

Correct:

```text
dim_pub_date
dim_trade_customer
```

Incorrect:

```text
dim_customer           # no pub or domain segment
dim_sales_customer     # 'sales' is not a declared domain
```

Source: Alibaba dim-layer · Spec §7
Checked by: DWH-N01, DWH-N03

### STD-02-03 DWD names (MUST)

`dwd_{domain}_{process}_{di|df}`, where process and domain match the process's entry in `warehouse/processes.yml`.
The DWD's `config.meta.process` names that entry.

Correct:

```yaml
models:
  - name: dwd_trade_order_di
    config:
      meta: {process: order}   # processes.yml: order, domain trade
```

Incorrect:

```yaml
models:
  - name: dwd_trade_orders_di    # process is 'order', not 'orders'
    config:
      meta: {process: order}
```

Source: Alibaba data-warehouse-detail-layer · Spec §7
Checked by: DWH-N01, DWH-N03, DWH-B02

### STD-02-04 DWS names carry one period (MUST)

`dws_{domain}_{grain}[_{custom}]_{period}` with period one of `1d`, `nd`, `td`, `1w`, `hh`, `mm`. A DWS table holds
one statistical period, and the period in the name is the period of every metric column in it.

Correct:

```text
dws_trade_customer_1d
dws_trade_customer_td
```

Incorrect:

```text
dws_trade_customer_daily    # 'daily' is not a period token
dws_trade_customer          # no period
```

Source: Alibaba data-warehouse-service-layer
Checked by: DWH-N01, DWH-M05

### STD-02-05 ADS names (MUST)

`ads_{app}_{subject}[_{period}]`. The application comes first. A period suffix, when present, is one of the six
period tokens; a trailing token that looks like a period but is not one (for example `30d`) is an error.

Correct:

```text
ads_finance_payment_export
ads_finance_payment_summary_1d
```

Incorrect:

```text
ads_payment_summary_30d     # 30d is not a period token; use nd and name the days in the metric
```

Source: Spec §7
Checked by: DWH-N01

### STD-02-06 History tables (MUST)

`_hist` names belong only to snapshots, and every snapshot is named `dim_..._hist`. A snapshot builds the SCD type 4
history table; the current table `dim_...` is a normal model with the same name without the suffix.

Correct:

```text
dim_trade_customer          # model, current rows
dim_trade_customer_hist     # snapshot, all versions
```

Incorrect:

```text
dim_trade_customer_hist     # a model, not a snapshot
customer_history            # a snapshot without the dim_..._hist name
```

Source: Kimball (type 4 history table) · Spec §2
Checked by: DWH-N04

### STD-02-07 Glossary words (MUST)

Outside ODS, every token of a model or column name is a word in `warehouse/glossary.yml`; so is every name in the
warehouse YAML. Period tokens (`1d`, `30d`, `hh`), the layer prefixes, `di`, `df`, `pub` and `hist` need no entry.
A new word is added to the glossary in the same PR, with its meaning.

Correct:

```yaml
# warehouse/glossary.yml
words:
  - {word: order, meaning: A customer order.}
  - {word: pay, meaning: To settle an order.}
```

Incorrect:

```text
dwd_trade_ordr_di      # 'ordr' is not in the glossary: a typo is caught, not stored
```

Source: Alibaba overall-process · Spec §7
Checked by: DWH-N05, DWH-N06, DWH-Y05

### STD-02-08 Column suffixes (SHOULD)

Use `_id` for natural ids, `_key` for surrogate or durable keys, `is_` for flags, `_date` for dates, `_at` for
timestamps, `_amt` for money and `_cnt` for counts. The suffix tells the type before the reader opens the schema.

Correct:

```sql
select order_id, customer_key, is_paid, order_date, created_at, pay_amt, item_cnt
```

Incorrect:

```sql
select orderno, customer, paid, odate, create_time, payment, items   -- no suffix says the type
```

Source: Spec §7

### STD-02-09 Metric column names (MUST)

A derived metric and its column are named `{modifiers}_{atomic}_{agg}_{period}`, with agg `sum`, `cnt`, `dcnt`, `min`
or `max`, and an `nd` period written as `<days>d`. The checker computes the expected name from the metric's
definition and compares it; a metric column in DWS or ADS must carry the metric's name.

Correct:

```yaml
# warehouse/metrics.yml
derived:
  - name: pay_amt_sum_1d
    atomic: pay_amt
    period: 1d
    grain: [customer]
    description: Payment amount per customer per day.
```

Incorrect:

```yaml
derived:
  - name: pay_amt_total_1d    # agg must be sum, cnt, dcnt, min or max
    atomic: pay_amt
    period: 1d
    grain: [customer]
    description: Payment amount per customer per day.
```

Source: Alibaba data-warehouse-service-layer · Spec §7
Checked by: DWH-M01, DWH-M04
