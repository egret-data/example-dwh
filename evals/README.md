# Skill scenarios

Headless scenarios that check whether the process skills change an agent's behaviour.

```bash
./evals/run.sh <scenario> [--ref <git-ref>] [--model <model>] [--without-skills] [--tool claude]
./evals/grade.py evals/scenarios/<scenario>.md evals/results/<answer>.md [--samples N]
./evals/summary.py <sha>
make eval SCENARIO=<name> [REF=<ref>] [WITHOUT_SKILLS=1]
make eval-all
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
- `summary.py <sha>` writes `results/summary-<sha>.md`: per scenario and model, the criteria met with and without skills, and
  whether the scenario discriminates (passes with skills, fails without).
- `make eval-all` (`run-all.sh`) runs every scenario both ways at `HEAD`, grades and summarises. Each agent run and
  each judge call is a paid `claude -p` call: 2 runs and 6 judge calls per scenario.
- Answers, grades and summaries go to `results/` (git-ignored).

## Evals follow-ups

- **Several agent runs per side.** One agent run per side is too noisy to call a scenario passing or discriminating.
  Run each side k times (for example k=3) and decide by majority or pass rate.
- **Measured noise** (plan 4, Task 8): with 3-sample judging, only 3 of about 70 criterion decisions split. But
  single agent runs flipped between commits with nearly identical skills: start-urgent-pressure,
  verify-before-done and scaffold-dws passed, then failed, with skills; debug-number-mismatch and
  reuse-derived-metric failed, then passed, without skills.
