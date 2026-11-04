"""The subset of dbt's manifest.json (schema v12) that the lint rules read."""

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

LAYERS = ("ods", "dim", "dwd", "dws", "ads")


@dataclass(frozen=True)
class Column:
    name: str
    description: str
    meta: dict


@dataclass(frozen=True)
class Node:
    """A model or a snapshot of the root project."""

    unique_id: str
    name: str
    resource_type: str
    path: str
    description: str
    meta: dict
    columns: dict[str, Column]
    depends_on: tuple[str, ...]
    contract_enforced: bool

    @property
    def layer(self) -> str | None:
        """models/<layer>/...; snapshots are DIM history tables (spec D11)."""
        if self.resource_type == "snapshot":
            return "dim"
        parts = PurePosixPath(self.path).parts
        if len(parts) >= 3 and parts[0] == "models" and parts[1] in LAYERS:
            return parts[1]
        return None

    @property
    def folder(self) -> str | None:
        """The folder under the layer: models/<layer>/<folder>/<file>."""
        parts = PurePosixPath(self.path).parts
        return parts[2] if len(parts) >= 4 and parts[0] == "models" else None


@dataclass(frozen=True)
class SourceTable:
    unique_id: str
    source_name: str
    name: str
    description: str
    meta: dict
    path: str


@dataclass(frozen=True)
class DataTest:
    unique_id: str
    name: str
    namespace: str | None
    attached_node: str | None
    column_name: str | None
    kwargs: dict


@dataclass(frozen=True)
class Project:
    nodes: dict[str, Node]
    sources: dict[str, SourceTable]
    tests: tuple[DataTest, ...]

    def models(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.resource_type == "model"]

    def refs(self, node: Node) -> list[Node]:
        return [self.nodes[d] for d in node.depends_on if d in self.nodes]

    def source_deps(self, node: Node) -> list[SourceTable]:
        return [self.sources[d] for d in node.depends_on if d in self.sources]

    def tests_for(self, unique_id: str) -> list[DataTest]:
        return [t for t in self.tests if t.attached_node == unique_id]


def load_manifest(path: Path) -> Project:
    manifest = json.loads(Path(path).read_text())
    project = manifest["metadata"]["project_name"]
    nodes: dict[str, Node] = {}
    tests: list[DataTest] = []
    for uid, raw in manifest["nodes"].items():
        if raw.get("package_name") != project:
            continue
        kind = raw["resource_type"]
        if kind in ("model", "snapshot"):
            nodes[uid] = Node(
                unique_id=uid,
                name=raw["name"],
                resource_type=kind,
                path=raw["original_file_path"],
                description=raw.get("description") or "",
                meta=raw.get("meta") or {},
                columns={
                    name: Column(name, c.get("description") or "", c.get("meta") or {})
                    for name, c in (raw.get("columns") or {}).items()
                },
                depends_on=tuple((raw.get("depends_on") or {}).get("nodes") or []),
                contract_enforced=bool((raw.get("contract") or {}).get("enforced")),
            )
        elif kind == "test" and raw.get("test_metadata"):
            meta = raw["test_metadata"]
            kwargs = meta.get("kwargs") or {}
            tests.append(
                DataTest(
                    unique_id=uid,
                    name=meta["name"],
                    namespace=meta.get("namespace"),
                    attached_node=raw.get("attached_node"),
                    column_name=raw.get("column_name") or kwargs.get("column_name"),
                    kwargs=kwargs,
                )
            )
    sources = {
        uid: SourceTable(
            unique_id=uid,
            source_name=raw["source_name"],
            name=raw["name"],
            description=raw.get("description") or "",
            meta=raw.get("meta") or {},
            path=raw["original_file_path"],
        )
        for uid, raw in manifest["sources"].items()
        if raw.get("package_name") == project
    }
    return Project(nodes, sources, tuple(tests))
