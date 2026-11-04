# Design record: the `date` dimension

- **Date:** 2026-11-04
- **Change class:** model-extending (adds a conformed dimension to `warehouse/dimensions.yml`)
- **Approved by:** the project owner, as part of the spec amendments of 2026-11-04 (spec §11, Kimball gap 8)

## Decision

`date` is a mandatory, shared (`pub`) dimension. It is built later as `dim_pub_date`, with one row per calendar
day in the Asia/Ho_Chi_Minh calendar (spec D12, §7 `04-dimensions.md`).

| Field | Value |
|-------|-------|
| scope | `pub` |
| natural key | `cal_date` |
| history | `scd1`: calendar facts never change |
| attributes | `year`, `month`, `weekday` (all `current`) |

The `dim_pub_date` model itself is out of scope for plan 2. It arrives with the reference domain in plan 4.

## Why

Every fact table needs a conformed date. Role-playing uses of it, such as `order_date`, are declared in
`bus_matrix.yml`. `dwh validate` rule DWH-Y04 enforces that this dimension exists.
