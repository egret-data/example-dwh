#!/usr/bin/env python3
"""Summarise graded eval runs for one commit.

    evals/summary.py <sha>

Reads evals/results/<scenario>-<sha>-<model>[-noskills].grade.json and writes evals/results/summary-<sha>.md:
per scenario, the criteria met with and without skills, and whether the scenario discriminates (passes with
skills, fails without).
"""

import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def cell(result: dict | None) -> str:
    if result is None:
        return "missing"
    met = sum(e["met"] for e in result["pass"])
    hit = sum(e["hit"] for e in result["fail"])
    verdict = "PASS" if result["passed"] else "FAIL"
    return f"pass {met}/{len(result['pass'])}, fail {hit}/{len(result['fail'])}: {verdict}"


def rows(results: Path, sha: str) -> dict[str, dict]:
    """Map scenario -> {"with": grade, "without": grade, "discriminates": bool}; a missing run is None."""
    found: dict[str, dict] = {}
    for path in sorted(Path(results).glob(f"*-{sha}-*.grade.json")):
        stem = path.name.removesuffix(".grade.json")
        scenario = stem.split(f"-{sha}-", 1)[0]
        side = "without" if stem.endswith("-noskills") else "with"
        found.setdefault(scenario, {"with": None, "without": None})[side] = json.loads(path.read_text())
    for row in found.values():
        row["discriminates"] = bool(
            row["with"] and row["without"] and row["with"]["passed"] and not row["without"]["passed"]
        )
    return found


def build_table(found: dict[str, dict]) -> str:
    lines = [
        "| Scenario | With skills | Without skills | Discriminates |",
        "|----------|-------------|----------------|---------------|",
    ]
    for scenario, row in sorted(found.items()):
        lines.append(
            f"| {scenario} | {cell(row['with'])} | {cell(row['without'])} | "
            f"{'yes' if row['discriminates'] else 'no'} |"
        )
    return "\n".join(lines) + "\n"


def failures(found: dict[str, dict]) -> str:
    """List the criteria that decided each FAIL, so a reader can see why without opening the JSON."""
    out = []
    for scenario, row in sorted(found.items()):
        for side in ("with", "without"):
            result = row[side]
            if not result or result["passed"]:
                continue
            missed = [f"not met: {e['criterion']}" for e in result["pass"] if not e["met"]]
            hit = [f"hit: {e['criterion']}" for e in result["fail"] if e["hit"]]
            out.append(f"- **{scenario}** ({side} skills): " + "; ".join(missed + hit))
    return "\n".join(out) + "\n" if out else "None.\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: evals/summary.py <sha>", file=sys.stderr)
        return 2
    sha = argv[0]
    found = rows(RESULTS, sha)
    if not found:
        print(f"no grade files for {sha} in {RESULTS}", file=sys.stderr)
        return 1
    passing = sum(bool(r["with"] and r["with"]["passed"]) for r in found.values())
    discriminating = sum(r["discriminates"] for r in found.values())
    text = (
        f"# Eval summary {sha}\n\n"
        f"Passes with skills: {passing}/{len(found)}. Discriminates: {discriminating}/{len(found)}.\n\n"
        "Cells: Pass criteria met / total, Fail criteria hit / total, verdict.\n\n"
        + build_table(found)
        + "\n## Failed criteria\n\n"
        + failures(found)
    )
    out = RESULTS / f"summary-{sha}.md"
    out.write_text(text)
    print(text)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
