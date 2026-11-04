# Skill scenarios

Headless scenarios that check whether the process skills change an agent's behaviour.

```bash
./evals/run.sh <scenario> [--ref <git-ref>] [--model <model>]
make eval SCENARIO=<name> [REF=<ref>]
```

- Each scenario in `scenarios/` has a `## Prompt` (sent to the agent), `## Pass if` and `## Fail if` (graded by a human).
- The run sees the repository at `--ref` (default `HEAD`) with `fixtures/<fixture>` copied over it, and read-only tools.
- Use the commit before the skills existed as `--ref` for a RED baseline.
- Answers go to `results/<scenario>-<sha>-<model>.md`, which is git-ignored.
