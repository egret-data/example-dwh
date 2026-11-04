"""`dwh check-standards`: the rulebook format (spec §7) and its link to the lint codes (DWH-R)."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from dwh.codes import CODES
from dwh.findings import Finding, rel

STANDARD_FILES = (
    "00-principles.md",
    "01-layers.md",
    "02-naming.md",
    "03-domains-bus-matrix.md",
    "04-dimensions.md",
    "05-facts.md",
    "06-metrics.md",
    "07-dws-ads.md",
    "08-iceberg-incremental.md",
    "09-dbt-conventions.md",
    "10-trino-sql-style.md",
    "11-airflow.md",
    "12-data-quality.md",
)
# Pages with body text in the Alibaba "Build and optimize a data warehouse" section (research digest).
ALIBABA_SLUGS = frozenset(
    {
        "overall-process",
        "determine-business-requirements",
        "analyze-business-processes",
        "divide-data-domains",
        "define-dimensions-and-build-a-bus-matrix",
        "specify-statistical-metrics",
        "select-a-technical-architecture",
        "divide-a-data-warehouse-into-layers",
        "specify-the-principles-for-using-data-at-different-layers",
        "dim-layer",
        "data-warehouse-detail-layer",
        "data-warehouse-service-layer",
        "project-allocation-and-security",
        "performance-benchmark-establishment",
        "data-warehouse-performance-optimization",
        "result-verification",
    }
)
HEADING = re.compile(
    r"^### (?P<id>STD-(?P<file>\d\d)-(?P<n>\d\d)) (?P<title>\S.*) \((?P<level>MUST|SHOULD)\)$"
)
CODE = re.compile(r"\bDWH-[A-Z]\d\d\b")


@dataclass(frozen=True)
class Rule:
    id: str
    file_number: str
    lines: tuple[str, ...]


def split_rules(text: str) -> tuple[list[Rule], list[str]]:
    """Rules, plus the `### ` headings that are not valid rule headings. Fenced headings are ignored."""
    rules: list[Rule] = []
    bad: list[str] = []
    current: tuple[str, str] | None = None
    body: list[str] = []
    in_fence = False

    def close() -> None:
        if current is not None:
            rules.append(Rule(current[0], current[1], tuple(body)))

    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and (line.startswith("### ") or line.startswith("## ")):
            close()
            current, body = None, []
            if line.startswith("### "):
                match = HEADING.match(line)
                if match:
                    current = (match["id"], match["file"])
                else:
                    bad.append(line)
            continue
        if current is not None:
            body.append(line)
    close()
    return rules, bad


def has_example(lines: tuple[str, ...], label: str) -> bool:
    for i, line in enumerate(lines):
        if line.strip() == f"{label}:":
            following = [nxt for nxt in lines[i + 1 :] if nxt.strip()]
            return bool(following) and following[0].startswith("```")
    return False


def source_problem(lines: tuple[str, ...]) -> str | None:
    sources = [line for line in lines if line.startswith("Source: ")]
    if not sources:
        return "no Source: line"
    parts = [part.strip() for part in sources[0].removeprefix("Source: ").split("·")]
    for part in parts:
        if part.startswith("Alibaba"):
            slug = part.removeprefix("Alibaba").strip().split(" ")[0]
            if slug not in ALIBABA_SLUGS:
                return f"unknown Alibaba page {slug!r}"
    if not any(p.startswith(("Kimball", "Alibaba ", "Spec §")) for p in parts):
        return "Source: must cite Kimball, Alibaba <slug> or Spec §"
    return None


def cited_codes(lines: tuple[str, ...]) -> set[str]:
    checked = [line for line in lines if line.startswith("Checked by: ")]
    return set(CODE.findall(checked[0])) if checked else set()


def check_file(path: Path, seen: set[str]) -> Iterator[Finding | str]:
    """Findings for one file; also yields every cited code as a bare string."""
    where = rel(path)
    rules, bad = split_rules(path.read_text())
    for heading in bad:
        yield Finding(
            where, "DWH-R02", f"malformed rule heading {heading!r}: use '### STD-NN-MM <title> (MUST|SHOULD)'"
        )
    for rule in rules:
        if rule.file_number != path.name[:2]:
            yield Finding(
                where, "DWH-R02", f"{rule.id}: rule number must start with this file's number {path.name[:2]}"
            )
        if rule.id in seen:
            yield Finding(where, "DWH-R02", f"{rule.id}: duplicate rule id")
        seen.add(rule.id)
        for label in ("Correct", "Incorrect"):
            if not has_example(rule.lines, label):
                yield Finding(where, "DWH-R03", f"{rule.id}: no '{label}:' line followed by a fenced example")
        problem = source_problem(rule.lines)
        if problem:
            yield Finding(where, "DWH-R04", f"{rule.id}: {problem}")
        for code in sorted(cited_codes(rule.lines)):
            if code not in CODES:
                yield Finding(where, "DWH-R05", f"{rule.id}: unknown lint code {code}")
            else:
                yield code


def check_standards(root: Path, require_all: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    cited: set[str] = set()
    seen: set[str] = set()
    for name in STANDARD_FILES:
        path = root / name
        if not path.is_file():
            if require_all:
                findings.append(Finding(rel(path), "DWH-R01", "required standards file is missing"))
            continue
        for item in check_file(path, seen):
            if isinstance(item, Finding):
                findings.append(item)
            else:
                cited.add(item)
    if require_all:
        for code in sorted(CODES):
            if not code.startswith("DWH-R") and code not in cited:
                findings.append(
                    Finding(rel(root), "DWH-R06", f"{code} ({CODES[code]}) is not cited by any rule")
                )
    return sorted(set(findings))
