"""Spec §6.3: a PR that adds a domain, process, dimension or atomic metric needs an approved design."""

import re
import subprocess
from pathlib import Path

import yaml

from dwh.findings import Finding
from dwh.warehouse import FILES, Warehouse

LABEL = "design-approved"
CONCEPTS = (
    ("domains", "domains", "domain"),
    ("processes", "processes", "process"),
    ("dimensions", "dimensions", "dimension"),
    ("metrics", "atomic", "atomic metric"),
)
DESIGN_LINK = re.compile(r"docs/designs/[\w./-]+?\.md")


def added_concepts(base: Warehouse, head: Warehouse) -> list[str]:
    added = []
    for file, key, label in CONCEPTS:
        new = [name for name in head.by_name(file, key) if name not in base.by_name(file, key)]
        added += [f"{label} {name}" for name in new]
    return added


def check_gate(added: list[str], *, body: str, labels: list[str], repo_root: Path) -> list[Finding]:
    if not added:
        return []
    what = ", ".join(added)
    findings = []
    if LABEL not in labels:
        findings.append(Finding("warehouse/", "DWH-G01", f"adds {what}: the PR needs the label {LABEL}"))
    links = [link for link in DESIGN_LINK.findall(body or "") if (repo_root / link).is_file()]
    if not links:
        findings.append(
            Finding(
                "warehouse/",
                "DWH-G02",
                f"adds {what}: the PR description must link an existing docs/designs/*.md",
            )
        )
    return findings


def load_warehouse_at(ref: str, warehouse_rel: str, repo_root: Path) -> Warehouse:
    """The warehouse YAML as of git `ref`. Raises ValueError for an unknown ref."""
    check = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode != 0:
        raise ValueError(f"unknown git ref {ref!r}")
    data = {}
    for name in FILES:
        shown = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{ref}:{warehouse_rel}/{name}.yml"],
            capture_output=True,
            text=True,
            check=False,
        )
        data[name] = yaml.safe_load(shown.stdout) if shown.returncode == 0 else {}
    return Warehouse(repo_root / warehouse_rel, data)
