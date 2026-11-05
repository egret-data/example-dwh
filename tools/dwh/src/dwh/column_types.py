"""Column types declared in a dbt project's YAML, for `dwh scaffold` (M-2).

A model column declares `data_type`; a source column declares `data_type` or `config.meta.data_type`
(or the older top-level `meta.data_type`).
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from dwh.rules.naming import PATTERNS


@dataclass(frozen=True)
class ColumnTypes:
    models: dict[str, dict[str, str]] = field(default_factory=dict)
    sources: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)

    def upstream_type(self, upstream: list[str], column: str) -> str | None:
        """The declared type of `column` in the first upstream model that declares it.

        An ODS model that does not declare the column falls back to its source table's declaration.
        """
        for model in upstream:
            declared = self.models.get(model, {}).get(column)
            if declared:
                return declared
            match = PATTERNS["ods"].match(model)
            if match:
                declared = self.sources.get((match["source"], match["table"]), {}).get(column)
                if declared:
                    return declared
        return None


def _source_column_type(column: dict) -> str | None:
    meta = (column.get("config") or {}).get("meta") or column.get("meta") or {}
    return column.get("data_type") or meta.get("data_type")


def load_column_types(project_dir: Path) -> ColumnTypes:
    """Every declared column type under `project_dir`/models and /snapshots; empty if there is none."""
    models: dict[str, dict[str, str]] = {}
    sources: dict[tuple[str, str], dict[str, str]] = {}
    files = [f for folder in ("models", "snapshots") for f in sorted((project_dir / folder).rglob("*.yml"))]
    for path in files:
        data = yaml.safe_load(path.read_text()) or {}
        for model in [*(data.get("models") or []), *(data.get("snapshots") or [])]:
            declared = {c["name"]: c["data_type"] for c in model.get("columns") or [] if c.get("data_type")}
            if declared:
                models.setdefault(model["name"], {}).update(declared)
        for source in data.get("sources") or []:
            for table in source.get("tables") or []:
                declared = {
                    c["name"]: kind for c in table.get("columns") or [] if (kind := _source_column_type(c))
                }
                if declared:
                    sources.setdefault((source["name"], table["name"]), {}).update(declared)
    return ColumnTypes(models, sources)
