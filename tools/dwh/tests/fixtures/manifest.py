"""Build dbt manifest dicts (schema v12 subset that dwh reads) without running dbt."""

import copy

PROJECT = "example_dwh"


def _columns(columns: dict | None) -> dict:
    out = {}
    for name, spec in (columns or {}).items():
        spec = {"description": spec} if isinstance(spec, str) else spec
        out[name] = {"name": name, "description": spec.get("description", ""), "meta": spec.get("meta", {})}
    return out


class ManifestBuilder:
    def __init__(self) -> None:
        self._nodes: dict[str, dict] = {}
        self._sources: dict[str, dict] = {}
        self._tests = 0

    def source(self, source_name, table, *, description="A source table.", meta=None) -> str:
        uid = f"source.{PROJECT}.{source_name}.{table}"
        self._sources[uid] = {
            "unique_id": uid,
            "resource_type": "source",
            "package_name": PROJECT,
            "source_name": source_name,
            "name": table,
            "description": description,
            "meta": dict(meta or {}),
            "original_file_path": f"models/ods/{source_name}/_{source_name}__sources.yml",
        }
        return uid

    def model(
        self,
        name,
        path,
        *,
        deps=(),
        columns=None,
        meta=None,
        contract=False,
        description="A model.",
        resource_type="model",
    ) -> str:
        uid = f"{resource_type}.{PROJECT}.{name}"
        self._nodes[uid] = {
            "unique_id": uid,
            "resource_type": resource_type,
            "package_name": PROJECT,
            "name": name,
            "original_file_path": path,
            "description": description,
            "meta": dict(meta or {}),
            "columns": _columns(columns),
            "depends_on": {"nodes": list(deps)},
            "contract": {"enforced": contract},
        }
        return uid

    def snapshot(self, name, path, **kwargs) -> str:
        return self.model(name, path, resource_type="snapshot", **kwargs)

    def test(self, test_name, model, *, column=None, namespace=None, **kwargs) -> str:
        self._tests += 1
        uid = f"test.{PROJECT}.{test_name}_{self._tests}"
        test_kwargs = dict(kwargs)
        if column:
            test_kwargs["column_name"] = column
        self._nodes[uid] = {
            "unique_id": uid,
            "resource_type": "test",
            "package_name": PROJECT,
            "name": f"{test_name}_{self._tests}",
            "attached_node": model,
            "column_name": column,
            "test_metadata": {"name": test_name, "namespace": namespace, "kwargs": test_kwargs},
            "depends_on": {"nodes": [model]},
        }
        return uid

    def unique(self, model, column) -> str:
        return self.test("unique", model, column=column)

    def not_null(self, model, column) -> str:
        return self.test("not_null", model, column=column)

    def unique_combo(self, model, columns) -> str:
        return self.test(
            "unique_combination_of_columns",
            model,
            namespace="dbt_utils",
            combination_of_columns=list(columns),
        )

    def relationships(self, model, column, to, field) -> str:
        return self.test("relationships", model, column=column, to=f"ref('{to.split('.')[-1]}')", field=field)

    def node(self, uid) -> dict:
        """The live node dict, for tests that break one property."""
        return self._nodes[uid]

    def source_node(self, uid) -> dict:
        return self._sources[uid]

    def find_tests(self, model, test_name, column=None) -> list[str]:
        return [
            uid
            for uid, n in self._nodes.items()
            if n["resource_type"] == "test"
            and n["attached_node"] == model
            and n["test_metadata"]["name"] == test_name
            and (column is None or n["column_name"] == column)
        ]

    def remove(self, uid) -> None:
        self._nodes.pop(uid)

    def build(self) -> dict:
        return {
            "metadata": {
                "project_name": PROJECT,
                "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json",
            },
            "nodes": copy.deepcopy(self._nodes),
            "sources": copy.deepcopy(self._sources),
        }


def good_project() -> tuple[ManifestBuilder, dict[str, str]]:
    """ODS -> SCD4 DIM -> DWD -> DWS -> ADS for fixtures.warehouse.MINIMAL; clean for every lint family."""
    b = ManifestBuilder()
    ids: dict[str, str] = {}
    ids["orders"] = b.source(
        "shop",
        "orders",
        meta={
            "timezone": "Asia/Ho_Chi_Minh",
            "load": "di",
            "watermark": "updated_at",
            "delete_handling": "soft_delete_flag",
        },
    )
    ids["customers"] = b.source(
        "shop",
        "customers",
        meta={
            "timezone": "Asia/Ho_Chi_Minh",
            "load": "df",
            "delete_handling": "none",
        },
    )

    ids["ods_orders"] = b.model(
        "ods_shop_orders_di",
        "models/ods/shop/ods_shop_orders_di.sql",
        deps=[ids["orders"]],
        columns={"order_id": "Order id.", "dt": "Partition date."},
    )
    b.unique_combo(ids["ods_orders"], ["order_id", "dt"])
    b.not_null(ids["ods_orders"], "order_id")
    b.not_null(ids["ods_orders"], "dt")

    ids["ods_customers"] = b.model(
        "ods_shop_customers_df",
        "models/ods/shop/ods_shop_customers_df.sql",
        deps=[ids["customers"]],
        columns={"customer_id": "Customer id.", "dt": "Partition date."},
    )
    b.unique_combo(ids["ods_customers"], ["customer_id", "dt"])
    b.not_null(ids["ods_customers"], "customer_id")
    b.not_null(ids["ods_customers"], "dt")

    ids["hist"] = b.snapshot(
        "dim_pub_customer_hist",
        "snapshots/dim_pub_customer_hist.yml",
        deps=[ids["ods_customers"]],
        columns={"customer_key": "Durable key.", "customer_id": "Customer id.", "city": "City."},
    )

    ids["dim_customer"] = b.model(
        "dim_pub_customer",
        "models/dim/pub/dim_pub_customer.sql",
        deps=[ids["ods_customers"]],
        contract=True,
        columns={"customer_key": "Durable key.", "customer_id": "Customer id.", "city": "City."},
    )
    b.unique(ids["dim_customer"], "customer_key")
    b.not_null(ids["dim_customer"], "customer_key")

    ids["dwd_order"] = b.model(
        "dwd_trade_order_di",
        "models/dwd/trade/dwd_trade_order_di.sql",
        deps=[ids["ods_orders"], ids["dim_customer"], ids["hist"]],
        contract=True,
        meta={"process": "order"},
        columns={
            "order_id": "Order id.",
            "customer_key": "Customer durable key.",
            "order_amt": "Order amount.",
            "dt": "Partition date.",
        },
    )
    b.unique_combo(ids["dwd_order"], ["order_id", "dt"])
    b.not_null(ids["dwd_order"], "order_id")
    b.not_null(ids["dwd_order"], "dt")
    b.relationships(ids["dwd_order"], "customer_key", ids["dim_customer"], "customer_key")

    ids["dws_customer"] = b.model(
        "dws_trade_customer_1d",
        "models/dws/trade/dws_trade_customer_1d.sql",
        deps=[ids["dwd_order"]],
        contract=True,
        meta={"grain": ["customer_key"]},
        columns={
            "customer_key": "Customer durable key.",
            "order_amt_sum_1d": {"description": "Order amount.", "meta": {"metric": "order_amt_sum_1d"}},
            "order_cnt_1d": {"description": "Orders.", "meta": {"metric": "order_cnt_1d"}},
            "dt": "Partition date.",
        },
    )
    b.unique_combo(ids["dws_customer"], ["customer_key", "dt"])
    b.not_null(ids["dws_customer"], "customer_key")
    b.not_null(ids["dws_customer"], "dt")
    b.relationships(ids["dws_customer"], "customer_key", ids["dim_customer"], "customer_key")

    ids["ads_customer"] = b.model(
        "ads_bi_customer_daily",
        "models/ads/bi/ads_bi_customer_daily.sql",
        deps=[ids["dws_customer"], ids["dim_customer"]],
        columns={
            "customer_key": "Customer durable key.",
            "city": "City.",
            "avg_order_amt_1d": {
                "description": "Average order amount.",
                "meta": {"metric": "avg_order_amt_1d"},
            },
            "dt": "Partition date.",
        },
    )
    b.unique_combo(ids["ads_customer"], ["customer_key", "dt"])
    b.not_null(ids["ads_customer"], "customer_key")
    b.not_null(ids["ads_customer"], "dt")
    return b, ids
