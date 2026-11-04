"""`dwh validate`: JSON Schema (DWH-Y01) first, then the cross-file YAML rules (DWH-Y02..)."""

import json
from collections.abc import Iterator
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from dwh.findings import Finding, rel
from dwh.warehouse import FILES, load_warehouse
from dwh.yaml_rules import YAML_RULES


def schema_findings(root: Path, schema_dir: Path) -> Iterator[Finding]:
    for name in FILES:
        path = root / f"{name}.yml"
        if not path.exists():
            yield Finding(rel(path), "DWH-Y01", "file is missing")
            continue
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            yield Finding(rel(path), "DWH-Y01", f"invalid YAML: {exc}")
            continue
        schema = json.loads((schema_dir / f"{name}.schema.json").read_text())
        for error in sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: e.json_path):
            yield Finding(rel(path), "DWH-Y01", f"{error.json_path}: {error.message}")


def validate(root: Path, schema_dir: Path | None = None) -> list[Finding]:
    """All DWH-Y findings for the warehouse at `root`. Cross-file rules run only on schema-valid YAML."""
    findings = list(schema_findings(root, schema_dir or root / "schemas"))
    if findings:
        return sorted(set(findings))
    warehouse = load_warehouse(root)
    return sorted({finding for rule in YAML_RULES for finding in rule(warehouse)})
