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
DESIGN_LINK = re.compile(r"(?:^|(?<=[\s(`]))docs/designs/[\w./-]+?\.md")


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
    designs = (repo_root / "docs" / "designs").resolve()
    links = [link for link in DESIGN_LINK.findall(body or "") if is_design_record(repo_root / link, designs)]
    if not links:
        findings.append(
            Finding(
                "warehouse/",
                "DWH-G02",
                f"adds {what}: the PR description must link an existing design record by repo-relative path, "
                "e.g. docs/designs/<record>.md (a GitHub URL is not accepted)",
            )
        )
    return findings


def is_design_record(path: Path, designs: Path) -> bool:
    resolved = path.resolve()
    return resolved.is_file() and resolved.is_relative_to(designs)


def load_warehouse_at(ref: str, warehouse_rel: str, repo_root: Path) -> Warehouse:
    """The warehouse YAML as of git `ref`. Raises ValueError for an unknown ref or malformed YAML."""
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
        try:
            data[name] = yaml.safe_load(shown.stdout) if shown.returncode == 0 else {}
        except yaml.YAMLError as exc:
            raise ValueError(f"{warehouse_rel}/{name}.yml at {ref} is not valid YAML: {exc}") from exc
    return Warehouse(repo_root / warehouse_rel, data)
