"""DWH-M: metric definitions and metric columns (spec §5, §7 06-metrics and 07-dws-ads)."""

from collections.abc import Iterator

from dwh.findings import Finding
from dwh.lint import Context
from dwh.rules.naming import PATTERNS

AGG_TOKEN = {"sum": "sum", "count": "cnt", "count_distinct": "dcnt", "min": "min", "max": "max"}


def metric_column(derived: dict, atomic: dict) -> str:
    """{modifiers}_{atomic}_{agg}_{period}; an nd period renders as <days>d."""
    period = f"{derived['days']}d" if derived["period"] == "nd" else derived["period"]
    return "_".join([*derived.get("modifiers", []), atomic["name"], AGG_TOKEN[atomic["aggregation"]], period])


def m01_derived_name(ctx: Context) -> Iterator[Finding]:
    wh = ctx.warehouse
    for derived in wh.derived.values():
        atomic = wh.atomic.get(derived["atomic"])
        if atomic is None:
            continue  # DWH-Y03
        expected = metric_column(derived, atomic)
        if derived["name"] != expected:
            yield Finding(
                wh.path("metrics"),
                "DWH-M01",
                f"derived metric {derived['name']}: name must be {expected} "
                "({modifiers}_{atomic}_{agg}_{period})",
            )


def m02_no_derived_on_non_additive(ctx: Context) -> Iterator[Finding]:
    wh = ctx.warehouse
    for derived in wh.derived.values():
        atomic = wh.atomic.get(derived["atomic"])
        if atomic and atomic["additivity"] == "non_additive":
            yield Finding(
                wh.path("metrics"),
                "DWH-M02",
                f"derived metric {derived['name']}: atomic metric {atomic['name']} is non-additive; "
                "store numerator and denominator as derived metrics and define the result as a "
                "calculated metric",
            )


def m03_dws_columns(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.models():
        if node.layer != "dws":
            continue
        grain = node.meta.get("grain")
        if not isinstance(grain, list) or not grain:
            yield Finding(
                node.path, "DWH-M03", f"{node.name}: DWS models declare meta.grain (their grain columns)"
            )
            grain = []
        for column in node.columns.values():
            if column.name in grain or column.name == "dt" or column.meta.get("metric"):
                continue
            yield Finding(
                node.path,
                "DWH-M03",
                f"{node.name}.{column.name}: DWS columns are grain columns, dt, or metrics (meta.metric)",
            )


def m04_metric_columns(ctx: Context) -> Iterator[Finding]:
    wh = ctx.warehouse
    for node in ctx.project.models():
        if node.layer not in ("dws", "ads"):
            continue
        for column in node.columns.values():
            metric = column.meta.get("metric")
            if not metric:
                continue
            if node.layer == "dws" and metric in wh.calculated:
                continue  # DWH-M06
            known = wh.derived if node.layer == "dws" else {**wh.derived, **wh.calculated}
            if metric not in known:
                kind = "derived" if node.layer == "dws" else "derived or calculated"
                yield Finding(
                    node.path,
                    "DWH-M04",
                    f"{node.name}.{column.name}: meta.metric {metric!r} is not a {kind} metric",
                )
            elif column.name != metric:
                yield Finding(
                    node.path, "DWH-M04", f"{node.name}.{column.name}: column must be named {metric}"
                )


def m05_one_period_per_dws(ctx: Context) -> Iterator[Finding]:
    wh = ctx.warehouse
    for node in ctx.project.models():
        match = PATTERNS["dws"].match(node.name) if node.layer == "dws" else None
        if match is None:
            continue
        for column in node.columns.values():
            derived = wh.derived.get(column.meta.get("metric"))
            if derived and derived["period"] != match["period"]:
                yield Finding(
                    node.path,
                    "DWH-M05",
                    f"{node.name}.{column.name}: metric period {derived['period']} differs from the "
                    f"table period {match['period']} (one statistical period per DWS table)",
                )


def m06_no_calculated_in_dwd_dws(ctx: Context) -> Iterator[Finding]:
    wh = ctx.warehouse
    for node in ctx.project.models():
        if node.layer not in ("dwd", "dws"):
            continue
        for column in node.columns.values():
            metric = column.meta.get("metric")
            if metric in wh.calculated:
                yield Finding(
                    node.path,
                    "DWH-M06",
                    f"{node.name}.{column.name}: calculated metric {metric} must not be stored in "
                    f"{node.layer}; store its inputs and compute it in ADS or BI",
                )


RULES = [
    m01_derived_name,
    m02_no_derived_on_non_additive,
    m03_dws_columns,
    m04_metric_columns,
    m05_one_period_per_dws,
    m06_no_calculated_in_dwd_dws,
]
