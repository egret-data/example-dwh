"""The eval grader and summary: scenario parsing, judge verdicts, pass/fail and discrimination."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"evals_{name}", REPO / "evals" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


grade = load("grade")
summary = load("summary")

SCENARIO = """# Scenario: demo

skills: dwh-start

## Prompt

Do the thing.

## Pass if

- States a class.
- Checks `warehouse/metrics.yml`
  before proposing.

## Fail if

- Writes SQL first.
"""


def fake_judge(verdict: dict) -> str:
    return f'{sys.executable} -c \'print("```json\\n" + {json.dumps(json.dumps(verdict))} + "\\n```")\''


def write_scenario(tmp_path: Path) -> Path:
    path = tmp_path / "demo.md"
    path.write_text(SCENARIO)
    return path


def test_sections_parses_pass_and_fail_bullets(tmp_path):
    scenario = write_scenario(tmp_path)

    parsed = grade.sections(scenario.read_text())

    assert parsed["prompt"] == "Do the thing."
    assert parsed["pass"] == ["States a class.", "Checks `warehouse/metrics.yml` before proposing."]
    assert parsed["fail"] == ["Writes SQL first."]


def test_every_scenario_has_pass_and_fail_criteria_and_no_fixture():
    for path in sorted((REPO / "evals" / "scenarios").glob("*.md")):
        parsed = grade.sections(path.read_text())
        assert parsed["prompt"], path.name
        assert parsed["pass"], path.name
        assert parsed["fail"], path.name
        assert "fixture:" not in path.read_text(), path.name


def test_parse_verdict_accepts_json_in_a_fenced_block():
    text = 'Here is my verdict:\n```json\n{"pass": [], "fail": []}\n```\n'

    assert grade.parse_verdict(text) == {"pass": [], "fail": []}


def test_parse_verdict_rejects_text_without_json():
    with pytest.raises(ValueError):
        grade.parse_verdict("All criteria look fine to me.")


@pytest.mark.parametrize(
    ("fail_hit", "expected"),
    [(False, True), (True, False)],
    ids=["all-met", "fail-hit"],
)
def test_grade_writes_grade_json_with_passed(tmp_path, monkeypatch, fail_hit, expected):
    scenario = write_scenario(tmp_path)
    answer = tmp_path / "demo-abc1234-sonnet.md"
    answer.write_text("Class: reuse. I checked warehouse/metrics.yml.")
    verdict = {
        "pass": [
            {"criterion": "States a class.", "met": True, "evidence": "Class: reuse."},
            {"criterion": "Checks metrics", "met": True, "evidence": "I checked warehouse/metrics.yml."},
        ],
        "fail": [{"criterion": "Writes SQL first.", "hit": fail_hit, "evidence": "-"}],
    }
    monkeypatch.setenv("DWH_EVAL_JUDGE", fake_judge(verdict))

    result = grade.grade(scenario, answer)

    written = json.loads((tmp_path / "demo-abc1234-sonnet.grade.json").read_text())
    assert written == result
    assert written["passed"] is expected
    assert [c["criterion"] for c in written["pass"]] == [
        "States a class.",
        "Checks `warehouse/metrics.yml` before proposing.",
    ]


def test_grade_rejects_a_verdict_that_skips_a_criterion(tmp_path, monkeypatch):
    scenario = write_scenario(tmp_path)
    answer = tmp_path / "demo-abc1234-sonnet.md"
    answer.write_text("anything")
    verdict = {"pass": [{"criterion": "States a class.", "met": True, "evidence": "x"}], "fail": []}
    monkeypatch.setenv("DWH_EVAL_JUDGE", fake_judge(verdict))

    with pytest.raises(ValueError):
        grade.grade(scenario, answer)


def write_grade(path: Path, met: list[bool], hit: list[bool]) -> None:
    result = {
        "pass": [{"criterion": f"p{i}", "met": m, "evidence": ""} for i, m in enumerate(met)],
        "fail": [{"criterion": f"f{i}", "hit": h, "evidence": ""} for i, h in enumerate(hit)],
        "passed": all(met) and not any(hit),
    }
    path.write_text(json.dumps(result))


def test_build_table_marks_discrimination(tmp_path):
    write_grade(tmp_path / "demo-abc1234-sonnet.grade.json", [True, True], [False])
    write_grade(tmp_path / "demo-abc1234-sonnet-noskills.grade.json", [True, False], [True])
    write_grade(tmp_path / "flat-abc1234-sonnet.grade.json", [True], [False])
    write_grade(tmp_path / "flat-abc1234-sonnet-noskills.grade.json", [True], [False])

    rows = summary.rows(tmp_path, "abc1234")
    table = summary.build_table(rows)

    assert rows["demo"]["discriminates"] is True
    assert rows["flat"]["discriminates"] is False
    assert "| demo | pass 2/2, fail 0/1: PASS | pass 1/2, fail 1/1: FAIL | yes |" in table
    assert "| flat | pass 1/1, fail 0/1: PASS | pass 1/1, fail 0/1: PASS | no |" in table


def test_run_sh_accepts_only_the_claude_tool():
    result = subprocess.run(
        ["bash", str(REPO / "evals" / "run.sh"), "revenue-by-channel", "--tool", "cursor"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "claude" in result.stderr
