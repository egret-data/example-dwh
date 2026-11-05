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


def test_parse_verdict_ignores_text_after_the_object():
    text = '{"pass": [], "fail": []}\nNote: the {answer} was short.'

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


def sequence_judge(tmp_path: Path, outputs: list[str]) -> str:
    """A fake judge that prints outputs[n] on its n-th call; an output of "EXIT" exits 1 instead."""
    script = tmp_path / "judge.py"
    state = tmp_path / "calls"
    (tmp_path / "outputs.json").write_text(json.dumps(outputs))
    script.write_text(
        "import json, pathlib, sys\n"
        f"state = pathlib.Path({str(state)!r})\n"
        "n = int(state.read_text()) if state.exists() else 0\n"
        "state.write_text(str(n + 1))\n"
        f"out = json.loads(pathlib.Path({str(tmp_path / 'outputs.json')!r}).read_text())[n]\n"
        "sys.exit(1) if out == 'EXIT' else print(out)\n"
    )
    return f"{sys.executable} {script}"


def verdict_json(met: list[bool], hit: list[bool]) -> str:
    return json.dumps(
        {
            "pass": [{"criterion": "c", "met": m, "evidence": f"e{i}"} for i, m in enumerate(met)],
            "fail": [{"criterion": "c", "hit": h, "evidence": "e"} for h in hit],
        }
    )


def test_grade_decides_each_criterion_by_majority_of_three_samples(tmp_path, monkeypatch):
    scenario = write_scenario(tmp_path)
    answer = tmp_path / "demo-abc1234-sonnet.md"
    answer.write_text("anything")
    outputs = [
        verdict_json([True, False], [True]),
        verdict_json([True, True], [False]),
        verdict_json([False, True], [False]),
    ]
    monkeypatch.setenv("DWH_EVAL_JUDGE", sequence_judge(tmp_path, outputs))

    result = grade.grade(scenario, answer, samples=3)

    assert [e["met"] for e in result["pass"]] == [True, True]
    assert [e["votes"] for e in result["pass"]] == [[True, True, False], [False, True, True]]
    assert result["fail"][0]["hit"] is False
    assert result["fail"][0]["votes"] == [True, False, False]
    assert result["samples"] == 3
    assert result["passed"] is True


@pytest.mark.parametrize(
    "bad",
    ["EXIT", "no json here", verdict_json([True], [False]), json.dumps({"pass": ["x", "y"], "fail": ["z"]})],
    ids=["non-zero-exit", "no-json", "wrong-count", "non-object-entry"],
)
def test_grade_retries_a_malformed_verdict_once(tmp_path, monkeypatch, bad):
    scenario = write_scenario(tmp_path)
    answer = tmp_path / "demo-abc1234-sonnet.md"
    answer.write_text("anything")
    monkeypatch.setenv("DWH_EVAL_JUDGE", sequence_judge(tmp_path, [bad, verdict_json([True, True], [False])]))

    result = grade.grade(scenario, answer, samples=1)

    assert result["passed"] is True
    assert (tmp_path / "calls").read_text() == "2"


def test_grade_fails_after_two_malformed_verdicts(tmp_path, monkeypatch):
    scenario = write_scenario(tmp_path)
    answer = tmp_path / "demo-abc1234-sonnet.md"
    answer.write_text("anything")
    monkeypatch.setenv("DWH_EVAL_JUDGE", sequence_judge(tmp_path, ["no json", "still none"]))

    with pytest.raises(ValueError):
        grade.grade(scenario, answer, samples=1)


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

    assert rows[("demo", "sonnet")]["discriminates"] is True
    assert rows[("flat", "sonnet")]["discriminates"] is False
    assert "| demo | sonnet | pass 2/2, fail 0/1: PASS | pass 1/2, fail 1/1: FAIL | yes |" in table
    assert "| flat | sonnet | pass 1/1, fail 0/1: PASS | pass 1/1, fail 0/1: PASS | no |" in table


def test_rows_keep_two_models_of_one_sha_apart(tmp_path):
    write_grade(tmp_path / "demo-abc1234-sonnet.grade.json", [True], [False])
    write_grade(tmp_path / "demo-abc1234-haiku.grade.json", [False], [False])

    rows = summary.rows(tmp_path, "abc1234")

    assert rows[("demo", "sonnet")]["with"]["passed"] is True
    assert rows[("demo", "haiku")]["with"]["passed"] is False


def test_run_sh_accepts_only_the_claude_tool():
    result = subprocess.run(
        ["bash", str(REPO / "evals" / "run.sh"), "revenue-by-channel", "--tool", "cursor"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "claude" in result.stderr


# --- several agent runs per side (`--runs N`, `-r<k>` files, majority per side) ---


def test_summary_decides_each_side_by_majority_of_runs(tmp_path):
    for k, passed in enumerate([True, False, True], 1):
        write_grade(tmp_path / f"demo-abc1234-sonnet-r{k}.grade.json", [passed], [False])
    for k, passed in enumerate([False, False, True], 1):
        write_grade(tmp_path / f"demo-abc1234-sonnet-noskills-r{k}.grade.json", [passed], [False])

    rows = summary.rows(tmp_path, "abc1234")

    row = rows[("demo", "sonnet")]
    assert row["with"]["passed"] is True
    assert row["without"]["passed"] is False
    assert row["discriminates"] is True
    assert "| demo | sonnet | 2/3 runs pass: PASS | 1/3 runs pass: FAIL | yes |" in summary.build_table(rows)


def test_a_tie_between_runs_is_not_a_majority(tmp_path):
    write_grade(tmp_path / "demo-abc1234-sonnet-r1.grade.json", [True], [False])
    write_grade(tmp_path / "demo-abc1234-sonnet-r2.grade.json", [False], [False])

    rows = summary.rows(tmp_path, "abc1234")

    assert rows[("demo", "sonnet")]["with"]["passed"] is False
    assert rows[("demo", "sonnet")]["with"]["verdict"] == "TIE"
    assert len(rows[("demo", "sonnet")]["with"]["runs"]) == 2


def test_a_tied_baseline_does_not_discriminate(tmp_path):
    """A baseline that passes half its runs is not a FAIL, so the scenario does not discriminate (I-7)."""
    for k in (1, 2, 3):
        write_grade(tmp_path / f"demo-abc1234-sonnet-r{k}.grade.json", [True], [False])
    write_grade(tmp_path / "demo-abc1234-sonnet-noskills-r1.grade.json", [True], [False])
    write_grade(tmp_path / "demo-abc1234-sonnet-noskills-r2.grade.json", [False], [False])

    rows = summary.rows(tmp_path, "abc1234")

    assert rows[("demo", "sonnet")]["discriminates"] is False
    assert "| demo | sonnet | 3/3 runs pass: PASS | 1/2 runs pass: TIE | no |" in summary.build_table(rows)


def test_failures_count_the_runs_that_missed_each_criterion(tmp_path):
    write_grade(tmp_path / "demo-abc1234-sonnet-r1.grade.json", [False, True], [False])
    write_grade(tmp_path / "demo-abc1234-sonnet-r2.grade.json", [False, True], [True])
    write_grade(tmp_path / "demo-abc1234-sonnet-r3.grade.json", [True, True], [False])

    text = summary.failures(summary.rows(tmp_path, "abc1234"))

    assert "**demo** (sonnet, with skills)" in text
    assert "not met in 2/3 runs: p0" in text
    assert "hit in 1/3 runs: f0" in text
    assert "p1" not in text


def fake_claude(tmp_path: Path) -> Path:
    """A `claude` on PATH that answers 'GOOD' on odd calls and 'BAD' on even calls (counted per side)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "claude"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "cat >/dev/null\n"
        "side=skills; [ -e AGENTS.md ] || side=noskills\n"
        'state="$FAKE_STATE/$side"\n'
        'n=$(( $(cat "$state" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$state"\n'
        'if [ "$side" = skills ] && [ "$n" != 2 ]; then word=GOOD; else word=BAD; fi\n'
        'echo "$word answer $n"\n'
    )
    script.chmod(0o755)
    return bin_dir


def keyword_judge(tmp_path: Path) -> str:
    """A fake judge: every Pass criterion met when the answer says GOOD, none when it says BAD."""
    script = tmp_path / "keyword_judge.py"
    script.write_text(
        "import json, re, sys\n"
        "prompt = sys.stdin.read()\n"
        "answer = prompt.split('<answer>', 1)[1]\n"
        "met = 'GOOD' in answer\n"
        "rubric = prompt.split('Pass criteria:', 1)[1].split('<answer>', 1)[0]\n"
        "pass_text, fail_text = rubric.split('Fail criteria:', 1)\n"
        "passes = re.findall(r'^\\d+\\. ', pass_text, re.M)\n"
        "fails = re.findall(r'^\\d+\\. ', fail_text, re.M)\n"
        "print(json.dumps({'pass': [{'criterion': 'c', 'met': met, 'evidence': 'e'} for _ in passes],\n"
        "                  'fail': [{'criterion': 'c', 'hit': False, 'evidence': 'e'} for _ in fails]}))\n"
    )
    return f"{sys.executable} {script}"


def eval_env(tmp_path: Path) -> dict:
    import os

    state = tmp_path / "state"
    state.mkdir()
    results = tmp_path / "results"
    return {
        **os.environ,
        "PATH": f"{fake_claude(tmp_path)}:{os.environ['PATH']}",
        "FAKE_STATE": str(state),
        "DWH_EVAL_RESULTS": str(results),
        "DWH_EVAL_JUDGE": keyword_judge(tmp_path),
        "DWH_EVAL_SAMPLES": "1",
    }


def head_sha() -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def test_run_sh_writes_one_numbered_answer_per_run(tmp_path):
    env = eval_env(tmp_path)

    result = subprocess.run(
        ["bash", str(REPO / "evals" / "run.sh"), "revenue-by-channel", "--runs", "3"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    base = Path(env["DWH_EVAL_RESULTS"]) / f"revenue-by-channel-{head_sha()}-sonnet"
    assert [Path(f"{base}-r{k}.md").read_text().strip() for k in (1, 2, 3)] == [
        "GOOD answer 1",
        "BAD answer 2",
        "GOOD answer 3",
    ]
    assert not Path(f"{base}.md").exists()


def test_run_sh_removes_the_runs_of_an_earlier_invocation(tmp_path):
    env = eval_env(tmp_path)
    run = ["bash", str(REPO / "evals" / "run.sh"), "revenue-by-channel", "--runs"]
    base = Path(env["DWH_EVAL_RESULTS"]) / f"revenue-by-channel-{head_sha()}-sonnet"

    assert subprocess.run([*run, "3"], capture_output=True, text=True, env=env).returncode == 0
    Path(f"{base}-r3.grade.json").write_text("{}")
    assert subprocess.run([*run, "1"], capture_output=True, text=True, env=env).returncode == 0

    assert sorted(p.name for p in base.parent.iterdir()) == [f"{base.name}-r1.md"]


@pytest.mark.parametrize("runs", ["0", "x", "-1"])
def test_run_sh_rejects_a_bad_run_count(tmp_path, runs):
    result = subprocess.run(
        ["bash", str(REPO / "evals" / "run.sh"), "revenue-by-channel", "--runs", runs],
        capture_output=True,
        text=True,
        env=eval_env(tmp_path),
    )

    assert result.returncode == 2
    assert "--runs takes a positive integer" in result.stderr


def test_run_all_grades_every_run_and_summarises_by_majority(tmp_path):
    env = eval_env(tmp_path)

    result = subprocess.run(
        ["bash", str(REPO / "evals" / "run-all.sh"), "--runs", "3", "--scenario", "revenue-by-channel"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    results = Path(env["DWH_EVAL_RESULTS"])
    sha = head_sha()
    grades = sorted(p.name for p in results.glob("*.grade.json"))
    assert grades == sorted(
        f"revenue-by-channel-{sha}-sonnet{side}-r{k}.grade.json"
        for side in ("", "-noskills")
        for k in (1, 2, 3)
    )
    text = (results / f"summary-{sha}.md").read_text()
    assert "| revenue-by-channel | sonnet | 2/3 runs pass: PASS | 0/3 runs pass: FAIL | yes |" in text
