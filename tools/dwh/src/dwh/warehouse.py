"""Load warehouse/*.yml (spec §5) into one read-only object."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from dwh.findings import rel

FILES = ("domains", "processes", "dimensions", "bus_matrix", "metrics", "modifiers", "periods", "glossary")


@dataclass(frozen=True)
class Warehouse:
    root: Path
    data: dict[str, Any]

    def path(self, name: str) -> str:
        return rel(self.root / f"{name}.yml")

    def items(self, file: str, key: str) -> list[dict]:
        return list((self.data.get(file) or {}).get(key) or [])

    def by_name(self, file: str, key: str) -> dict[str, dict]:
        return {item["name"]: item for item in self.items(file, key)}

    @property
    def domains(self) -> dict[str, dict]:
        return self.by_name("domains", "domains")

    @property
    def processes(self) -> dict[str, dict]:
        return self.by_name("processes", "processes")

    @property
    def dimensions(self) -> dict[str, dict]:
        return self.by_name("dimensions", "dimensions")

    @property
    def modifier_types(self) -> dict[str, dict]:
        return self.by_name("modifiers", "modifier_types")

    @property
    def modifiers(self) -> dict[str, dict]:
        return self.by_name("modifiers", "modifiers")

    @property
    def atomic(self) -> dict[str, dict]:
        return self.by_name("metrics", "atomic")

    @property
    def derived(self) -> dict[str, dict]:
        return self.by_name("metrics", "derived")

    @property
    def calculated(self) -> dict[str, dict]:
        return self.by_name("metrics", "calculated")

    @property
    def periods(self) -> dict[str, dict]:
        return self.by_name("periods", "periods")

    @property
    def words(self) -> set[str]:
        return {item["word"] for item in self.items("glossary", "words")}

    @property
    def bus(self) -> dict[str, dict]:
        return {row["process"]: row for row in self.items("bus_matrix", "bus_matrix")}


def load_warehouse(root: Path) -> Warehouse:
    data = {}
    for name in FILES:
        path = root / f"{name}.yml"
        data[name] = yaml.safe_load(path.read_text()) if path.exists() else {}
    return Warehouse(root, data)
