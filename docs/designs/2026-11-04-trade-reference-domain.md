# Design record: the `trade` reference domain

- **Date:** 2026-11-04
- **Change class:** model-extending (adds domains `trade` and `crm`, three processes, two dimensions, metrics)
- **Status:** awaiting data-architect approval (`design-approved` label); no SQL is written before it

## Request

A reference domain for the team and for skill evals: shop orders and payments, from the `shop` Postgres source
through ODS, DIM, DWD, DWS and one ADS. Consumers:

- BI (finance dashboard) reads DWD + DIM;
- the CRM customer-value export reads the ADS.

## Business process

| Process | Fact type | Event |
|---------|-----------|-------|
| `order` | transaction | A customer places an order in a shop. |
| `payment` | transaction | A payment for an order is captured. |
| `order_lifecycle` | accumulating snapshot | An order moves from placed to paid. |

## Grain

- `order`: one row per order, on the Asia/Ho_Chi_Minh day it was placed.
- `payment`: one row per payment, on the day it was captured.
- `order_lifecycle`: one row per order, updated when it is paid.

All three are atomic. The DWS tables below are summaries built on the atomic DWD, not new facts.

## Dimensions (reused / new)

| Dimension | Scope | Status | History | Natural key | Attributes |
|-----------|-------|--------|---------|-------------|------------|
| `date` | pub | reused | scd1 | `cal_date` | year, month, weekday (current) |
| `customer` | pub | new | scd4 | `customer_id` | `customer_name` current; `city` historical |
| `shop` | trade | new | scd1 | `shop_id` | `shop_name`, `city` current |

- `customer.city` is historical because an order must show the city the customer had when ordering (STD-05-05).
  The SCD4 `_hist` snapshot serves the point-in-time join. `customer_name` is only read now, so it stays current.
- `shop` is owned by `trade` (only trade uses it) and has no history: shops are looked up as they are today.
- Roles (bus matrix): `order` uses `date` as `order_date`; `payment` uses `date` as `pay_date`; `order_lifecycle`
  uses `date` twice (`order_date`, `pay_date`). All three use `customer` and `shop`.
- Every dimension has the `'-1'` Unknown and `'-2'` Not applicable members (STD-04-06).

## Metrics (reused / new)

All new; nothing in `metrics.yml` existed before.

| Kind | Name | Definition |
|------|------|------------|
| atomic | `order_amt` | process `order`, sum, additive |
| atomic | `order` | process `order`, count, additive |
| atomic | `pay_amt` | process `payment`, sum, additive |
| derived | `order_amt_sum_1d` | `order_amt`, 1d, grain `customer` |
| derived | `order_cnt_1d` | `order`, 1d, grain `customer` |
| derived | `app_order_amt_sum_1d` | `order_amt`, 1d, modifier `app`, grain `customer` |
| derived | `order_amt_sum_30d` | `order_amt`, nd (30 days), grain `customer` |
| derived | `order_amt_sum_td` | `order_amt`, td, grain `customer` |
| derived | `order_cnt_td` | `order`, td, grain `customer` |
| calculated | `avg_order_amt_td` | `order_amt_sum_td / nullif(order_cnt_td, 0)` |

Modifier type `channel` (domain `trade`); modifier `app` (`channel = 'app'`, process `order`). `pay_amt` has no
derived form yet: no consumer asked for one.

## Sources

All timestamps are naive Vietnam local time (Asia/Ho_Chi_Minh).

| Source table | Load | Watermark | Deletes |
|--------------|------|-----------|---------|
| `shop.orders` | di | `updated_at` | none observed; status `cancelled` is a state, not a delete |
| `shop.payments` | di | insert-only (`updated_at` = `paid_at`) | none |
| `shop.customers` | df | none (full copy per day) | full copy shows the current state |
| `shop.shops` | df | none (full copy per day) | full copy shows the current state |

Orders 2 and 4 of the fixture are first loaded after the day they were placed. The event DWDs partition by the
event time, so the dwh-backfill rerun (oldest `dt` first) is how they land in the right partition (STD-05-08).

## Consumers

- BI finance dashboard: DWD + DIM.
- CRM customer-value export: `ads_crm_customer_value`.

## Tables

Partition is `dt` unless noted. "Partition replacement" deletes the `dt` partition and appends. Layers and names
follow `02-naming`.

| Layer | Model | Grain | Keys | Columns | Upstream | Load / history |
|-------|-------|-------|------|---------|----------|----------------|
| DIM | `dim_pub_date` | one row per calendar day 2020-01-01..2030-12-31, plus `-1`, `-2` | `date_key` (surrogate of `cal_date`) | `date_key`, `cal_date`, `year`, `month`, `weekday` | none (generated) | full table; scd1; hand-written (scaffold needs an upstream) |
| DIM | `dim_pub_customer` | one current row per customer, plus `-1`, `-2` | `customer_key` (durable hash of `customer_id`) | `customer_key`, `customer_id`, `customer_name`, `city`, `updated_at` | `ods_shop_customers_df` | full table; scd4 |
| DIM | `dim_pub_customer_hist` | one row per customer version | `customer_key`, `valid_from` | `customer_key`, `customer_name`, `city`, `valid_from`, `valid_to` | `dim_pub_customer` | timestamp snapshot on `updated_at`; all versions |
| DIM | `dim_trade_shop` | one current row per shop, plus `-1`, `-2` | `shop_key` (hash of `shop_id`) | `shop_key`, `shop_id`, `shop_name`, `city` | `ods_shop_shops_df` | full table; scd1 |
| DWD | `dwd_trade_order_di` | one row per order, on its placed day | `order_id`; `dt` | `order_id`, `order_date_key`, `customer_key`, `shop_key`, `channel`, `order_status`, `order_amt`, `customer_city` (historical), `created_at`, `dt` | `ods_shop_orders_di`, `dim_pub_customer_hist` (point-in-time city; keys are hashes, no other DIM join) | partition replacement on `dt` = `created_at` day; point-in-time city (STD-05-05) |
| DWD | `dwd_trade_payment_di` | one row per payment, on its captured day | `payment_id`; `dt` | `payment_id`, `order_id` (degenerate), `pay_date_key`, `customer_key`, `shop_key`, `pay_amt`, `method`, `paid_at`, `dt` | `ods_shop_payments_di` (carries `customer_id` and `shop_id`; a transaction DWD must not read another DWD, STD-01-03) | partition replacement on `dt` = `paid_at` day |
| DWD | `dwd_trade_order_lifecycle_di` | one row per order, updated when paid | `order_id`; `dt` = order event day | `order_id`, `order_date_key`, `pay_date_key` (`-2` when unpaid), `customer_key`, `shop_key`, `order_amt`, `pay_amt`, `created_at`, `paid_at`, `is_paid`, `dt` | `dwd_trade_order_di`, `dwd_trade_payment_di` | merge on `order_id`; hand-written (accumulating snapshot); reads DWD only (STD-01-05) |
| DWS | `dws_trade_customer_1d` | one row per customer per day | `customer_key`; `dt` | `customer_key`, `order_amt_sum_1d`, `order_cnt_1d`, `app_order_amt_sum_1d`, `dt` | `dwd_trade_order_di` | partition replacement |
| DWS | `dws_trade_customer_nd` | one row per customer per day | `customer_key`; `dt` | `customer_key`, `order_amt_sum_30d`, `dt` | `dwd_trade_order_di` | partition replacement; 30-day window ending on `dt` |
| DWS | `dws_trade_customer_td` | one row per customer per day | `customer_key`; `dt` | `customer_key`, `order_amt_sum_td`, `order_cnt_td`, `dt` | `dwd_trade_order_di` | partition replacement; all history up to `dt` |
| ADS | `ads_crm_customer_value` | one row per customer per day | `customer_key`; `dt` | `customer_key`, `order_amt_sum_td`, `order_cnt_td`, `avg_order_amt_td`, `dt` | `dws_trade_customer_td` | full table rebuilt each run (ADS, STD-09-01); serves the CRM customer-value export (STD-07-05) |

`ods_shop_shops_df` and `ods_shop_payments_di` already exist from plan 4 task 2.

## DWS justification (STD-07-04)

The DWS tables have two consumers: the ADS `ads_crm_customer_value` (reads `dws_trade_customer_td`) and the
finance dashboard. One period per table: 1d, nd (30d) and td are three separate tables.

## Open questions

None.
