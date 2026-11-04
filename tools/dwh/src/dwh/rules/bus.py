"""DWH-B: every DWD maps to a business process and its bus-matrix row (spec §5, §7 03)."""

from collections.abc import Iterator

from dwh.findings import Finding
from dwh.lint import Context
from dwh.rules.naming import PATTERNS


def dwd_models(ctx: Context):
    return [n for n in ctx.project.models() if n.layer == "dwd"]


def process_of(node) -> str | None:
    """meta.process when it is a non-empty string; anything else counts as undeclared."""
    process = node.meta.get("process")
    return process if isinstance(process, str) and process else None


def b01_dwd_declares_a_process(ctx: Context) -> Iterator[Finding]:
    for node in dwd_models(ctx):
        process = process_of(node)
        if not process:
            yield Finding(
                node.path, "DWH-B01", f"{node.name}: DWD models declare meta.process (from processes.yml)"
            )
        elif process not in ctx.warehouse.processes:
            yield Finding(node.path, "DWH-B01", f"{node.name}: unknown process {process!r}")


def b02_dwd_name_matches_process(ctx: Context) -> Iterator[Finding]:
    for node in dwd_models(ctx):
        process = ctx.warehouse.processes.get(process_of(node))
        match = PATTERNS["dwd"].match(node.name)
        if process is None or match is None:
            continue
        if match["domain"] != process["domain"] or match["process"] != process["name"]:
            yield Finding(
                node.path,
                "DWH-B02",
                f"{node.name}: process {process['name']} of domain {process['domain']} is loaded into "
                f"dwd_{process['domain']}_{process['name']}_{{di|df}}",
            )


def b03_process_in_bus_matrix(ctx: Context) -> Iterator[Finding]:
    for node in dwd_models(ctx):
        process = process_of(node)
        if process in ctx.warehouse.processes and process not in ctx.warehouse.bus:
            yield Finding(
                node.path, "DWH-B03", f"{node.name}: process {process} has no row in bus_matrix.yml"
            )


def b04_keys_are_bus_dimensions(ctx: Context) -> Iterator[Finding]:
    for node in dwd_models(ctx):
        row = ctx.warehouse.bus.get(process_of(node))
        if row is None:
            continue
        allowed = {c["dimension"] for c in row["dimensions"]} | {
            c["role"] for c in row["dimensions"] if "role" in c
        }
        for column in sorted(node.columns):
            if column.endswith("_key") and column[: -len("_key")] not in allowed:
                yield Finding(
                    node.path,
                    "DWH-B04",
                    f"{node.name}.{column}: {column[: -len('_key')]!r} is not a dimension or role of process "
                    f"{row['process']} in bus_matrix.yml",
                )


RULES = [
    b01_dwd_declares_a_process,
    b02_dwd_name_matches_process,
    b03_process_in_bus_matrix,
    b04_keys_are_bus_dimensions,
]
