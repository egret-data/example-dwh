"""A small, coherent warehouse design. Tests copy it and break one thing at a time."""

import copy
from collections.abc import Callable, Iterable
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[4]
SCHEMAS = REPO / "warehouse" / "schemas"

WORDS = (
    "ods dim dwd dws ads pub hist di df dt id key is at amt cnt dcnt sum min max avg "
    "date cal year month weekday name inferred trade order shipment ship customer city shop "
    "app channel buyer bi daily status"
).split()

MINIMAL: dict = {
    "domains": {"domains": [{"name": "trade", "description": "Orders and shipments.", "owner": "data-eng"}]},
    "processes": {
        "processes": [
            {
                "name": "order",
                "domain": "trade",
                "description": "A buyer places an order.",
                "fact_type": "transaction",
                "grain": "One row per order.",
            },
            {
                "name": "shipment",
                "domain": "trade",
                "description": "An order moves from placed to delivered.",
                "fact_type": "accumulating_snapshot",
                "grain": "One row per order, updated at each milestone.",
            },
        ]
    },
    "dimensions": {
        "dimensions": [
            {
                "name": "date",
                "scope": "pub",
                "description": "Calendar day.",
                "natural_key": ["cal_date"],
                "history": "scd1",
                "attributes": [{"name": "year", "description": "Year.", "history": "current"}],
            },
            {
                "name": "customer",
                "scope": "pub",
                "description": "A buyer.",
                "natural_key": ["customer_id"],
                "history": "scd4",
                "attributes": [{"name": "city", "description": "City.", "history": "historical"}],
            },
            {
                "name": "shop",
                "scope": "trade",
                "description": "A shop.",
                "natural_key": ["shop_id"],
                "history": "scd1",
                "attributes": [{"name": "shop_name", "description": "Shop name.", "history": "current"}],
            },
        ]
    },
    "bus_matrix": {
        "bus_matrix": [
            {
                "process": "order",
                "dimensions": [
                    {"dimension": "date", "role": "order_date"},
                    {"dimension": "customer"},
                    {"dimension": "shop"},
                ],
            },
            {
                "process": "shipment",
                "dimensions": [{"dimension": "date", "role": "ship_date"}, {"dimension": "customer"}],
            },
        ]
    },
    "metrics": {
        "atomic": [
            {
                "name": "order_amt",
                "process": "order",
                "description": "Order amount.",
                "aggregation": "sum",
                "additivity": "additive",
            },
            {
                "name": "order",
                "process": "order",
                "description": "Orders.",
                "aggregation": "count",
                "additivity": "additive",
            },
            {
                "name": "order_buyer",
                "process": "order",
                "description": "Distinct buyers.",
                "aggregation": "count_distinct",
                "additivity": "non_additive",
            },
        ],
        "derived": [
            {
                "name": "order_amt_sum_1d",
                "atomic": "order_amt",
                "period": "1d",
                "grain": ["customer"],
                "description": "Order amount per customer per day.",
            },
            {
                "name": "app_order_amt_sum_30d",
                "atomic": "order_amt",
                "period": "nd",
                "days": 30,
                "modifiers": ["app"],
                "grain": ["customer"],
                "description": "App order amount per customer, last 30 days.",
            },
            {
                "name": "order_cnt_1d",
                "atomic": "order",
                "period": "1d",
                "grain": ["customer"],
                "description": "Orders per customer per day.",
            },
        ],
        "calculated": [
            {
                "name": "avg_order_amt_1d",
                "formula": "order_amt_sum_1d / order_cnt_1d",
                "inputs": ["order_amt_sum_1d", "order_cnt_1d"],
                "description": "Average order amount per customer per day.",
            }
        ],
    },
    "modifiers": {
        "modifier_types": [{"name": "channel", "domain": "trade", "description": "Sales channel."}],
        "modifiers": [
            {
                "name": "app",
                "type": "channel",
                "predicate": "channel = 'app'",
                "processes": ["order"],
                "description": "Orders placed in the mobile app.",
            }
        ],
    },
    "periods": {
        "periods": [{"name": p, "description": f"Period {p}."} for p in ("1d", "nd", "td", "1w", "hh", "mm")]
    },
    "glossary": {"words": [{"word": w, "meaning": f"Meaning of {w}."} for w in WORDS]},
}


def write_warehouse(
    directory: Path, mutate: Callable[[dict], None] | None = None, drop: Iterable[str] = ()
) -> Path:
    """Write MINIMAL (after `mutate`) as YAML files into `directory`, linking the real schemas."""
    files = copy.deepcopy(MINIMAL)
    if mutate:
        mutate(files)
    directory.mkdir(parents=True)
    (directory / "schemas").symlink_to(SCHEMAS, target_is_directory=True)
    for name, data in files.items():
        if name not in drop:
            (directory / f"{name}.yml").write_text(yaml.safe_dump(data, sort_keys=False))
    return directory
