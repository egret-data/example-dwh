# Plan 2 - warehouse lint verification

Measured on 2026-11-04 at the fix-wave head (see the commit that adds this file; it changes only this file
and follows `08808c4`). One chain run in bash on a fresh stack (`make dev-down` first):

```bash
bash -c 'set -o pipefail; make dev-down && make lint && make test-repo && make dwh-test && make validate \
  && make dwh-lint && make catalog && make image && make dev-up && make smoke && make test-dags \
  && make test-integration && make e2e; echo EXIT=$?'   # -> EXIT=0
```

| Step | Result |
|------|--------|
| `make lint` | All checks passed |
| `make test-repo` | 2 passed |
| `make dwh-test` | 115 passed |
| `make validate`, `make dwh-lint` | 0 finding(s) each |
| `make catalog` | wrote `site/index.html` (host dbt from `requirements-dbt.lock`) |
| `make test-dags` | 9 passed |
| `make test-integration` | 10 passed (includes the pushdown test) |
| `make e2e` | e2e OK |

An earlier run of the same chain stopped at `make test-dags` (4 failed: DagBag import timeout of 30 s while the
machine load average was above 20, right after a cold `make image`). The same step passed on rerun (9 passed)
and in the full chain above. It is a timing flake of the Cosmos parse under load, not a code failure.

## Plan-specific checks

- V1: `make e2e` logs `ods_shop_orders_di dt=2026-11-02 rows: "2"` for logical date 2026-11-03.
- V2: `5 of 5 PASS ods_shop_orders_di::orders_di_window_is_the_vietnam_day` inside the ODS build.
- V3: `iceberg.dev_ods.ods_shop_orders_di`: `created_at`, `updated_at` are `timestamp(6) with time zone`.
- V4: `Dockerfile` installs `requirements.lock` and `requirements-dbt.lock` with `--no-deps`, then runs
  `pip check` for both interpreters; `make image` succeeded.
- V5: `dwh lint --project-dir dags/dbt` on the real project reports 0 findings. Failing tests per code:
  B01 (3), B02, B03, B04 (2), D01, D02, D03, L01, L02, L03 (3), L04 (4), L05 (2), M01, M02, M03 (2), M04 (2),
  M05, M06, N01 (3), N02 (3), N03, N04 (2), N05, N06, S01 (2), S02, T01, T02, T03 (2), T04, Y01 (3), Y02, Y03 (3),
  Y04, Y05, Y06 - all in `tools/dwh/tests/test_rules_*.py` and `test_validate.py`, named `test_<code>_...`.
- V6: `test_gate_requires_the_label`, `test_gate_requires_a_link_to_an_existing_design_record` (plus the
  traversal, symlink and URL variants) fail the gate; `.github/workflows/design-gate.yml` triggers on
  `labeled` / `unlabeled` among its pull request types.
- V7: source pushdown of the dt window (F2). `EXPLAIN` of the ODS orders query against `shop.public.orders`:
  - before: `ScanFilterProject[table = shop:public.orders ..., filterPredicate = ((timestamp(6) with time zone
    '2026-11-03 00:00:00.000000 Asia/Ho_Chi_Minh' <= with_timezone(updated_at, ...)) AND (...))]` - no
    constraint, the whole table is scanned and filtered in Trino.
  - after: `TableScan[table = shop:public.orders shop.public.orders constraint on [updated_at] columns=[order_id ...]]`.
  `tests/integration/test_ods_shop.py::test_orders_window_is_pushed_down_to_the_source` asserts this on the
  compiled model (red against the old macro, green against the new one).

## Upgrade note

ODS tables built under plan 1 need `dbt build --full-refresh` once: their `_at` columns became
`timestamp(6) with time zone`.

## Known limits

- D02 cannot see columns that are missing from the `.yml`.
- The real project has only ODS models, so N05/N06, L04/L05, B and M are proven by fixtures only until plan 4.
- Done on 2026-11-04: `main` requires the `lint`, `stack` and `design-gate` checks (branch protection), and
  `.github/CODEOWNERS` requests the owner's review. Code-owner review is not required while the repo has one maintainer.
