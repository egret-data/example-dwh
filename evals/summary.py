#!/usr/bin/env python3
"""Summarise graded eval runs for one commit.

    evals/summary.py <sha>

Reads <scenario>-<sha>-<model>[-noskills][-r<k>].grade.json from $DWH_EVAL_RESULTS (default evals/results)
and writes summary-<sha>.md there: per scenario, the result with and without skills, and whether the scenario
discriminates (passes with skills, fails without).

Several agent runs of one side (`run.sh --runs N` writes `-r<k>` answers) are decided by strict majority: the
side passes when more than half of its runs pass, so a tie fails.
"""

import json
import os
import re
import sys
from pathlib import Path

RESULTS = Path(os.environ.get("DWH_EVAL_RESULTS") or Path(__file__).resolve().parent / "results")
RUN = re.compile(r"-r(\d+)$")


def side(runs: list[dict]) -> dict:
    """One side of a scenario: its runs and the majority verdict (more than half of the runs passed)."""
    passing = sum(run["passed"] for run in runs)
    return {"passed": passing * 2 > len(runs), "passing": passing, "runs": runs}


def cell(result: dict | None) -> str:
    if result is None:
        return "missing"
    if len(result["runs"]) > 1:
        verdict = "PASS" if result["passed"] else "FAIL"
        return f"{result['passing']}/{len(result['runs'])} runs pass: {verdict}"
    result = result["runs"][0]
    met = sum(e["met"] for e in result["pass"])
    hit = sum(e["hit"] for e in result["fail"])
    verdict = "PASS" if result["passed"] else "FAIL"
    return f"pass {met}/{len(result['pass'])}, fail {hit}/{len(result['fail'])}: {verdict}"


def rows(results: Path, sha: str) -> dict[tuple[str, str], dict]:
    """Map (scenario, model) -> {"with": side, "without": side, "discriminates": bool}.

    A side is `side(runs)`: every graded run of it (`-r<k>` files, or the single unnumbered one) and the
    majority verdict. A missing side is None.

    Keyed by model too, so runs of two models at one sha never overwrite each other.
    """
    runs: dict[tuple[str, str, str], list[dict]] = {}
    for path in sorted(Path(results).glob(f"*-{sha}-*.grade.json")):
        stem = RUN.sub("", path.name.removesuffix(".grade.json"))
        scenario, model = stem.split(f"-{sha}-", 1)
        which = "without" if model.endswith("-noskills") else "with"
        runs.setdefault((scenario, model.removesuffix("-noskills"), which), []).append(
            json.loads(path.read_text())
        )
    found: dict[tuple[str, str], dict] = {}
    for (scenario, model, which), graded in runs.items():
        found.setdefault((scenario, model), {"with": None, "without": None})[which] = side(graded)
    for row in found.values():
        row["discriminates"] = bool(
            row["with"] and row["without"] and row["with"]["passed"] and not row["without"]["passed"]
        )
    return found


def build_table(found: dict[tuple[str, str], dict]) -> str:
    lines = [
        "| Scenario | Model | With skills | Without skills | Discriminates |",
        "|----------|-------|-------------|----------------|---------------|",
    ]
    for (scenario, model), row in sorted(found.items()):
        lines.append(
            f"| {scenario} | {model} | {cell(row['with'])} | {cell(row['without'])} | "
            f"{'yes' if row['discriminates'] else 'no'} |"
        )
    return "\n".join(lines) + "\n"


def failures(found: dict[tuple[str, str], dict]) -> str:
    """List the criteria that decided each FAIL, so a reader can see why without opening the JSON."""
    out = []
    for (scenario, model), row in sorted(found.items()):
        for which in ("with", "without"):
            result = row[which]
            if not result or result["passed"]:
                continue
            graded = result["runs"]
            if len(graded) == 1:
                missed = [f"not met: {e['criterion']}" for e in graded[0]["pass"] if not e["met"]]
                hit = [f"hit: {e['criterion']}" for e in graded[0]["fail"] if e["hit"]]
            else:
                missed = counted(graded, "pass", "met", False, "not met")
                hit = counted(graded, "fail", "hit", True, "hit")
            out.append(f"- **{scenario}** ({model}, {which} skills): " + "; ".join(missed + hit))
    return "\n".join(out) + "\n" if out else "None.\n"


def counted(graded: list[dict], key: str, flag: str, bad: bool, label: str) -> list[str]:
    """`<label> in k/n runs: <criterion>` for each criterion that went wrong in at least one run."""
    out = []
    for i, entry in enumerate(graded[0][key]):
        wrong = sum(run[key][i][flag] is bad for run in graded)
        if wrong:
            out.append(f"{label} in {wrong}/{len(graded)} runs: {entry['criterion']}")
    return out


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
    multi = any(len(r[w]["runs"]) > 1 for r in found.values() for w in ("with", "without") if r[w])
    discriminating = sum(r["discriminates"] for r in found.values())
    text = (
        f"# Eval summary {sha}\n\n"
        f"Passes with skills: {passing}/{len(found)}. Discriminates: {discriminating}/{len(found)}.\n\n"
        "Cells: Pass criteria met / total, Fail criteria hit / total, verdict; each criterion is the "
        "majority of the judge samples recorded in its .grade.json.\n\n"
        + (
            "A side with several agent runs shows `k/n runs pass`; it passes when more than half of its runs "
            "pass.\n\n"
            if multi
            else ""
        )
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
