"""DWH-L: layer placement and dependency rules (spec §7, 01-layers)."""

from collections.abc import Iterator

from dwh.findings import Finding
from dwh.lint import Context
from dwh.manifest import LAYERS, Node

ALLOWED = {
    "dim": frozenset({"ods", "dim"}),
    "dwd": frozenset({"ods", "dim"}),
    "dws": frozenset({"dwd", "dim", "dws"}),
    "ads": frozenset({"dws", "dim"}),
}
SNAPSHOT_ALLOWED = frozenset({"ods"})
CDM = ("dim", "dwd", "dws")
MAX_DEPTH = 10


def is_accumulating(ctx: Context, node: Node) -> bool:
    process = ctx.warehouse.processes.get(node.meta.get("process"))
    return bool(process) and process["fact_type"] == "accumulating_snapshot"


def l01_layer_folder(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        if node.layer is None:
            yield Finding(
                node.path, "DWH-L01", f"{node.name}: models live under models/<{'|'.join(LAYERS)}>/"
            )


def l02_prefix_matches_layer(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        if node.layer and node.name.split("_", 1)[0] != node.layer:
            yield Finding(
                node.path, "DWH-L02", f"{node.name}: a {node.layer} model is named {node.layer}_..."
            )


def l03_sources_only_in_ods(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        if node.layer is None:
            continue
        sources, refs = ctx.project.source_deps(node), ctx.project.refs(node)
        if node.layer == "ods":
            if not sources:
                yield Finding(node.path, "DWH-L03", f"{node.name}: an ODS model reads a source()")
            for ref in refs:
                yield Finding(node.path, "DWH-L03", f"{node.name}: an ODS model must not ref {ref.name}")
        else:
            for source in sources:
                yield Finding(
                    node.path,
                    "DWH-L03",
                    f"{node.name}: only ODS models read source() ({source.source_name}.{source.name})",
                )


def l04_allowed_dependencies(ctx: Context) -> Iterator[Finding]:
    for node in ctx.project.nodes.values():
        if node.layer in (None, "ods"):
            continue
        allowed = SNAPSHOT_ALLOWED if node.resource_type == "snapshot" else ALLOWED[node.layer]
        accumulating = node.layer == "dwd" and is_accumulating(ctx, node)
        for dep in ctx.project.refs(node):
            if dep.layer is None:
                continue  # reported by DWH-L01
            if accumulating and dep.layer == "ods":
                yield Finding(
                    node.path,
                    "DWH-L04",
                    f"{node.name}: an accumulating snapshot reads transaction facts (DWD), "
                    f"not ODS ({dep.name})",
                )
                continue
            ok = (
                dep.layer in allowed
                or (accumulating and dep.layer == "dwd")
                or (node.layer == "ads" and dep.layer == "dwd" and bool(node.meta.get("dwd_reason")))
            )
            if not ok:
                yield Finding(
                    node.path, "DWH-L04", f"{node.name} ({node.layer}) must not read {dep.name} ({dep.layer})"
                )


def l05_chain_depth(ctx: Context) -> Iterator[Finding]:
    depth: dict[str, int] = {}

    def chain(node: Node) -> int:
        if node.unique_id not in depth:
            parents = [d for d in ctx.project.refs(node) if d.layer in CDM]
            depth[node.unique_id] = 1 + max((chain(p) for p in parents), default=0)
        return depth[node.unique_id]

    for node in ctx.project.nodes.values():
        if node.layer in CDM and chain(node) > MAX_DEPTH:
            yield Finding(
                node.path,
                "DWH-L05",
                f"{node.name}: dependency chain inside DIM/DWD/DWS is {chain(node)} models deep "
                f"(max {MAX_DEPTH})",
            )


RULES = [
    l01_layer_folder,
    l02_prefix_matches_layer,
    l03_sources_only_in_ods,
    l04_allowed_dependencies,
    l05_chain_depth,
]
