#!/usr/bin/env python3
"""Grade one eval answer against its scenario with an LLM judge.

    evals/grade.py <scenario.md> <answer.md> [--samples N]

Writes <answer>.grade.json next to the answer (``x.md`` -> ``x.grade.json``):
``{"pass": [{criterion, met, evidence, votes}], "fail": [{criterion, hit, evidence, votes}], "samples": N,
"passed": bool}``.
The judge is asked N times (``--samples``, default 3, env ``DWH_EVAL_SAMPLES``); each criterion is decided by
strict majority and its votes are recorded. ``passed`` is computed here from the majority, not by the judge:
every Pass criterion met and no Fail criterion hit.

The judge is ``claude -p`` (sonnet) in an empty temp dir with no tools and no settings, so it sees
neither this repository nor its instruction files. ``DWH_EVAL_JUDGE`` overrides the judge command (tests
use a fake one); the prompt goes to its stdin.
"""

import argparse
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
    # Otherwise decode from each opening brace, ignoring any text after the object.
    candidates += [text[i:] for i, char in enumerate(text) if char == "{"]
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            verdict, _ = decoder.raw_decode(candidate.strip())
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
    if not all(isinstance(entry, dict) for entry in given):
        raise ValueError(f"judge gave a non-object entry in {key!r}")
    return [
        {"criterion": criterion, flag: entry.get(flag) is True, "evidence": str(entry.get("evidence", ""))}
        for criterion, entry in zip(criteria, given, strict=True)
    ]


def judge_once(prompt: str, parsed: dict) -> dict:
    """One judge sample. A malformed verdict (non-zero exit, no JSON, wrong criterion count, a non-object
    entry) is retried once; a second failure raises."""
    for attempt in (1, 2):
        try:
            verdict = parse_verdict(ask_judge(prompt))
            return {
                "pass": entries(verdict, "pass", "met", parsed["pass"]),
                "fail": entries(verdict, "fail", "hit", parsed["fail"]),
            }
        except (ValueError, RuntimeError):
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def majority(samples: list[dict], key: str, flag: str) -> list[dict]:
    """Decide each criterion by strict majority of the samples; keep every vote and one agreeing evidence."""
    decided = []
    for i, first in enumerate(samples[0][key]):
        votes = [sample[key][i][flag] for sample in samples]
        value = sum(votes) * 2 > len(votes)
        evidence = next(s[key][i]["evidence"] for s in samples if s[key][i][flag] == value)
        decided.append({"criterion": first["criterion"], flag: value, "evidence": evidence, "votes": votes})
    return decided


def default_samples() -> int:
    return int(os.environ.get("DWH_EVAL_SAMPLES", "3"))


def grade(scenario: Path, answer: Path, samples: int | None = None) -> dict:
    samples = samples or default_samples()
    if samples < 1:
        raise ValueError("samples must be at least 1")
    parsed = sections(Path(scenario).read_text())
    answer = Path(answer)
    prompt = PROMPT.format(
        prompt=parsed["prompt"],
        pass_list="\n".join(f"{i}. {c}" for i, c in enumerate(parsed["pass"], 1)),
        fail_list="\n".join(f"{i}. {c}" for i, c in enumerate(parsed["fail"], 1)),
        answer=answer.read_text().strip(),
    )
    votes = [judge_once(prompt, parsed) for _ in range(samples)]
    result = {
        "pass": majority(votes, "pass", "met"),
        "fail": majority(votes, "fail", "hit"),
        "samples": samples,
    }
    result["passed"] = all(e["met"] for e in result["pass"]) and not any(e["hit"] for e in result["fail"])
    answer.with_suffix(".grade.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Grade one eval answer with an LLM judge.")
    parser.add_argument("scenario", type=Path)
    parser.add_argument("answer", type=Path)
    parser.add_argument(
        "--samples",
        type=int,
        default=default_samples(),
        help="judge calls per answer, decided by majority (default 3, env DWH_EVAL_SAMPLES)",
    )
    args = parser.parse_args(argv)
    result = grade(args.scenario, args.answer, args.samples)
    met = sum(e["met"] for e in result["pass"])
    hit = sum(e["hit"] for e in result["fail"])
    print(
        f"{args.answer}: pass {met}/{len(result['pass'])}, fail hit {hit}/{len(result['fail'])}: "
        f"{'PASS' if result['passed'] else 'FAIL'} (majority of {args.samples})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
