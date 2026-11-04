#!/usr/bin/env python3
"""Grade one eval answer against its scenario with an LLM judge.

    evals/grade.py <scenario.md> <answer.md>

Writes <answer>.grade.json next to the answer (``x.md`` -> ``x.grade.json``):
``{"pass": [{criterion, met, evidence}], "fail": [{criterion, hit, evidence}], "passed": bool}``.
``passed`` is computed here, not by the judge: every Pass criterion met and no Fail criterion hit.

The judge is ``claude -p`` (sonnet) in an empty temp dir with no tools and no settings, so it sees
neither this repository nor its instruction files. ``DWH_EVAL_JUDGE`` overrides the judge command (tests
use a fake one); the prompt goes to its stdin.
"""

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

JUDGE = [
    "claude",
    "-p",
    "--model",
    "sonnet",
    "--setting-sources",
    "",
    "--tools",
    "",
    "--strict-mcp-config",
    "--disable-slash-commands",
    "--no-session-persistence",
]

PROMPT = """You are grading an AI agent's answer to a data-warehouse request against a rubric.

Rules:
- Grade only from the answer text below. Do not assume the agent did anything the answer does not show.
- The agent ran with read-only tools: it could read files but not write them or run commands, so it may
  say that a write or a command was blocked. A criterion about writing, running or checking something is
  met when the answer gives that concrete step (the exact command, YAML entry, query or test) as what it
  will do or asks the user to run. A vague promise does not meet it.
- For each criterion, quote the evidence from the answer (a short verbatim excerpt), or write "none".
- A Pass criterion is met only when the answer clearly does what it says.
- A Fail criterion is hit when the answer does what it describes, even partly.
- Output only JSON, with one entry per criterion, in the order given, in this schema:

{{"pass": [{{"criterion": "...", "met": true, "evidence": "..."}}],
 "fail": [{{"criterion": "...", "hit": false, "evidence": "..."}}]}}

The request the agent received:

<request>
{prompt}
</request>

Pass criteria:
{pass_list}

Fail criteria:
{fail_list}

The agent's answer:

<answer>
{answer}
</answer>
"""


def sections(text: str) -> dict:
    """Split a scenario into its prompt and its Pass if / Fail if bullets (continuation lines are joined)."""
    found: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        heading = re.match(r"^## (.+?)\s*$", line)
        if heading:
            current = heading.group(1).strip().lower()
            found[current] = []
        elif current is not None:
            found[current].append(line)

    def bullets(lines: list[str]) -> list[str]:
        items: list[str] = []
        for line in lines:
            if line.startswith("- "):
                items.append(line[2:].strip())
            elif line.strip() and line.startswith(" ") and items:
                items[-1] += " " + line.strip()
        return items

    return {
        "prompt": "\n".join(found.get("prompt", [])).strip(),
        "pass": bullets(found.get("pass if", [])),
        "fail": bullets(found.get("fail if", [])),
    }


def parse_verdict(text: str) -> dict:
    """Return the judge's JSON object, from a fenced block or the outermost braces.

    Raises ValueError when the text holds no JSON object.
    """
    fenced = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            verdict = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(verdict, dict):
            return verdict
    raise ValueError(f"no JSON verdict in judge output: {text[:200]!r}")


def judge_command() -> list[str]:
    override = os.environ.get("DWH_EVAL_JUDGE")
    return shlex.split(override) if override else JUDGE


def ask_judge(prompt: str) -> str:
    with tempfile.TemporaryDirectory(prefix="dwh-eval-judge.") as empty:
        result = subprocess.run(
            judge_command(), input=prompt, capture_output=True, text=True, cwd=empty, check=False
        )
    if result.returncode != 0:
        raise RuntimeError(f"judge exited {result.returncode}: {result.stderr.strip()[:500]}")
    return result.stdout


def entries(verdict: dict, key: str, flag: str, criteria: list[str]) -> list[dict]:
    given = verdict.get(key)
    if not isinstance(given, list) or len(given) != len(criteria):
        raise ValueError(f"judge gave {key!r} for {len(given or [])} of {len(criteria)} criteria")
    return [
        {"criterion": criterion, flag: entry.get(flag) is True, "evidence": str(entry.get("evidence", ""))}
        for criterion, entry in zip(criteria, given, strict=True)
    ]


def grade(scenario: Path, answer: Path) -> dict:
    parsed = sections(Path(scenario).read_text())
    answer = Path(answer)
    prompt = PROMPT.format(
        prompt=parsed["prompt"],
        pass_list="\n".join(f"{i}. {c}" for i, c in enumerate(parsed["pass"], 1)),
        fail_list="\n".join(f"{i}. {c}" for i, c in enumerate(parsed["fail"], 1)),
        answer=answer.read_text().strip(),
    )
    verdict = parse_verdict(ask_judge(prompt))
    result = {
        "pass": entries(verdict, "pass", "met", parsed["pass"]),
        "fail": entries(verdict, "fail", "hit", parsed["fail"]),
    }
    result["passed"] = all(e["met"] for e in result["pass"]) and not any(e["hit"] for e in result["fail"])
    answer.with_suffix(".grade.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: evals/grade.py <scenario.md> <answer.md>", file=sys.stderr)
        return 2
    result = grade(Path(argv[0]), Path(argv[1]))
    met = sum(e["met"] for e in result["pass"])
    hit = sum(e["hit"] for e in result["fail"])
    print(
        f"{argv[1]}: pass {met}/{len(result['pass'])}, fail hit {hit}/{len(result['fail'])}: "
        f"{'PASS' if result['passed'] else 'FAIL'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
