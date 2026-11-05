"""Column types of a dbt project's models, for `dwh scaffold` (M-2).

A model's type for a column is what the model outputs:
1. the `data_type` its `.yml` declares;
2. for an ODS model, the type its `.sql` casts the column to: `cast(<c> as <type>) as <c>`,
   `{{ source_ts('<c>', tz) }} as <c>` or `date '{{ get_dt() }}' as dt`, one per line.

The source table's own types are never used: every ODS model re-casts its columns, so the source type is not
what a downstream model reads.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from dwh.rules.naming import PATTERNS

CAST = re.compile(r"^\s*cast\((\w+) as (.+?)\)\s+as (\w+),?\s*$", re.IGNORECASE)
SOURCE_TS = re.compile(r"^\s*\{\{\s*source_ts\('(\w+)',\s*\w+\)\s*\}\}\s+as (\w+),?\s*$")
DT = re.compile(r"^\s*date '\{\{\s*get_dt\(\)\s*\}\}'\s+as dt,?\s*$")
SOURCE_TS_TYPE = (
    "timestamp(6) with time zone"  # with_timezone(cast(c as timestamp(6)), tz), macros/business_day.sql
)


class ColumnTypeError(ValueError):
    """A project file cannot be read for column types."""


@dataclass(frozen=True)
class ColumnTypes:
    models: dict[str, dict[str, str]] = field(default_factory=dict)
    ods_casts: dict[str, dict[str, str]] = field(default_factory=dict)
    known: frozenset[str] = frozenset()

    def upstream_type(self, upstream: list[str], column: str) -> str | None:
        """The type of `column` in the first upstream model that declares or (ODS) casts it."""
        for model in upstream:
            found = self.models.get(model, {}).get(column) or self.ods_casts.get(model, {}).get(column)
            if found:
                return found
        return None

    def untypable_ods(self, upstream: list[str]) -> str | None:
        """The primary upstream if it is an ODS model of this project: its columns are never guessed."""
        primary = upstream[0] if upstream else ""
        return primary if PATTERNS["ods"].match(primary) and primary in self.known else None


def ods_casts(sql: str) -> dict[str, str]:
    """`column -> type` from an ODS select list; a column cast two different ways is left out (unreliable)."""
    found: dict[str, set[str]] = {}
    for line in sql.splitlines():
        cast = CAST.match(line)
        if cast and cast.group(1) == cast.group(3):
            found.setdefault(cast.group(3), set()).add(" ".join(cast.group(2).lower().split()))
            continue
        ts = SOURCE_TS.match(line)
        if ts and ts.group(1) == ts.group(2):
            found.setdefault(ts.group(2), set()).add(SOURCE_TS_TYPE)
        elif DT.match(line):
            found.setdefault("dt", set()).add("date")
    return {column: kinds.pop() for column, kinds in found.items() if len(kinds) == 1}


def load_column_types(project_dir: Path) -> ColumnTypes:
    """Every declared model column type and every ODS cast under `project_dir`; empty without a project."""
    models: dict[str, dict[str, str]] = {}
    casts: dict[str, dict[str, str]] = {}
    known: set[str] = set()
    for folder in ("models", "snapshots"):
        for path in sorted((project_dir / folder).rglob("*.yml")):
            data = yaml.safe_load(path.read_text())
            if data is None:
                continue
            if not isinstance(data, dict):
                raise ColumnTypeError(f"{path}: the top level is not a mapping")
            for model in [*(data.get("models") or []), *(data.get("snapshots") or [])]:
                if not isinstance(model, dict) or not model.get("name"):
                    continue
                known.add(model["name"])
                declared = {
                    c["name"]: str(c["data_type"]).strip()
                    for c in model.get("columns") or []
                    if isinstance(c, dict) and c.get("name") and c.get("data_type")
                }
                if declared:
                    models.setdefault(model["name"], {}).update(declared)
    for path in sorted((project_dir / "models").rglob("ods_*.sql")):
        known.add(path.stem)
        casts[path.stem] = ods_casts(path.read_text())
    return ColumnTypes(models, casts, frozenset(known))
