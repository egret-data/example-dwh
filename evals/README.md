# Skill scenarios

Headless scenarios that check whether the process skills change an agent's behaviour.

```bash
./evals/run.sh <scenario> [--ref <git-ref>] [--model <model>] [--without-skills] [--tool claude] [--runs N]
./evals/grade.py evals/scenarios/<scenario>.md evals/results/<answer>.md [--samples N]
./evals/summary.py <sha>
./evals/run-all.sh [--model <model>] [--runs N] [--scenario <name>]...
make eval SCENARIO=<name> [REF=<ref>] [WITHOUT_SKILLS=1] [RUNS=N]
make eval-all [RUNS=N]
```

- Each scenario in `scenarios/` has a `## Prompt` (sent to the agent), `## Pass if` and `## Fail if` bullets.
- `run.sh` runs the agent (Claude Code, read-only tools) on a throwaway worktree of `--ref` (default `HEAD`).
  `evals/`, `docs/en/plans/` and `docs/en/verification/` are removed, so the agent cannot read its rubric.
- `--without-skills` is the baseline: it also removes `skills/`, `.claude/`, `.cursor/`, `AGENTS.md`, `CLAUDE.md`,
  `GEMINI.md` and `.github/copilot-instructions.md`. `docs/standards/`, `docs/designs/` and `warehouse/` stay. The
  answer name gains `-noskills`.
- `--tool` is the seam for other agent tools; only `claude` is implemented.
- `grade.py` asks an LLM judge (`claude -p --model sonnet`) to grade the answer against the scenario's bullets and
  writes `<answer>.grade.json`. The judge runs in an empty temp dir with `--setting-sources ''`, `--tools ''`,
  `--strict-mcp-config` and `--disable-slash-commands`, so it loads no instruction files, settings, hooks or MCP
  servers and sees only the prompt. The judge is asked `--samples` times (default 3, env `DWH_EVAL_SAMPLES`), and
  each criterion is decided by strict majority; the `.grade.json` records every vote. `passed` is true when every
  Pass criterion is met and no Fail criterion is hit, by majority. A malformed verdict (non-zero exit, no JSON,
  wrong criterion count, a non-object entry) is retried once. `DWH_EVAL_JUDGE` overrides the judge command (the
  tests use a fake judge).
- `summary.py <sha>` writes `results/summary-<sha>.md`: per scenario and model, the result with and without
  skills, and whether the scenario discriminates (passes with skills, fails without).
- `--runs N` (on `run.sh` and `run-all.sh`) runs the agent N times per side and writes `<answer>-r1.md` …
  `<answer>-rN.md`; `run-all.sh` grades each run. `summary.py` decides each side by strict majority of its runs
  and shows `k/n runs pass`. An exact tie is `TIE`: neither a pass nor a fail, and never discriminating, so use an
  odd N. The failed-criteria list counts the runs that missed each criterion. Each `run.sh` call first removes that
  side's earlier answers and grades at the same sha. Without `--runs`, one run writes `<answer>.md` as before.
- `make eval-all` (`run-all.sh`) runs every scenario both ways at `HEAD`, grades and summarises. Each agent run and
  each judge call is a paid `claude -p` call: per scenario, 2 x N agent runs and 2 x N x 3 judge calls (N = 1
  without `--runs`). `--scenario <name>` (repeatable) limits the run to those scenarios.
- Answers, grades and summaries go to `results/` (git-ignored), or to `$DWH_EVAL_RESULTS` when it is set (the tests
  use a temp dir, a fake `claude` on `PATH` and a fake judge, so they spend nothing).

## Evals follow-ups

- **Several agent runs per side.** One agent run per side is too noisy to call a scenario passing or discriminating.
  `--runs N` (majority per side) now exists; no multi-run evaluation has been run yet (it is a budget decision).
- **Measured noise** (plan 4, Task 8): with 3-sample judging, only 3 of about 70 criterion decisions split. But
  single agent runs flipped between commits with nearly identical skills: start-urgent-pressure,
  verify-before-done and scaffold-dws passed, then failed, with skills; debug-number-mismatch and
  reuse-derived-metric failed, then passed, without skills.
