#!/usr/bin/env bash
# Run one skill scenario headless (spec §8.2) and save the answer for grading.
#   evals/run.sh <scenario> [--ref <git-ref>] [--model <model>] [--without-skills] [--tool claude] [--runs N]
# The run sees the repository at --ref (default HEAD) with read-only tools.
# --runs N runs the agent N times and writes one answer per run, <answer>-r1.md ... <answer>-rN.md; without it,
# one run writes <answer>.md. Answers go to $DWH_EVAL_RESULTS (default evals/results).
# --without-skills is the baseline: the same repository without the skills and the agent instruction files
# (docs/standards, docs/designs and warehouse/ stay).
# --tool is the seam for other agent tools; only claude is implemented.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
USAGE="usage: evals/run.sh <scenario> [--ref <git-ref>] [--model <model>] [--without-skills] [--tool claude] [--runs N]"
NAME=${1:?$USAGE}
shift
REF=HEAD
MODEL=sonnet
TOOL=claude
SKILLS=1
RUNS=
RUNS_GIVEN=
while [ $# -gt 0 ]; do
  case $1 in
    --ref) REF=$2; shift 2 ;;
    --model) MODEL=$2; shift 2 ;;
    --tool) TOOL=$2; shift 2 ;;
    --without-skills) SKILLS=0; shift ;;
    --runs) RUNS=${2-}; RUNS_GIVEN=1; shift; [ $# -gt 0 ] && shift ;;
    *) echo "unknown argument: $1" >&2; echo "$USAGE" >&2; exit 2 ;;
  esac
done
if [ -n "$RUNS_GIVEN" ] && ! [[ "$RUNS" =~ ^[1-9][0-9]*$ ]]; then
  echo "--runs takes a positive integer, got: $RUNS" >&2; exit 2
fi
[ "$TOOL" = claude ] || { echo "unsupported tool: $TOOL (only claude is implemented)" >&2; exit 2; }
SCENARIO="$REPO/evals/scenarios/$NAME.md"
[ -f "$SCENARIO" ] || { echo "no scenario $SCENARIO" >&2; exit 2; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/dwh-eval.XXXXXX")"
git -C "$REPO" worktree add --detach --quiet "$WORK/repo" "$REF"
trap 'git -C "$REPO" worktree remove --force "$WORK/repo"' EXIT

# The agent must not read its own grading rubric or the skill texts in the plans and verification records.
git -C "$WORK/repo" rm -r -q --ignore-unmatch evals docs/en/plans docs/en/verification
SUFFIX=
if [ "$SKILLS" = 0 ]; then
  git -C "$WORK/repo" rm -r -q --ignore-unmatch skills .claude .cursor AGENTS.md CLAUDE.md GEMINI.md \
    .github/copilot-instructions.md
  SUFFIX=-noskills
fi
# Commit the removals in the throwaway worktree so the agent sees a clean tree.
git -C "$WORK/repo" diff --cached --quiet \
  || git -C "$WORK/repo" -c user.name=dwh-eval -c user.email=dwh-eval@example.invalid \
    commit --quiet --no-verify -m "eval isolation${SUFFIX:+ without skills}"
PROMPT=$(sed -n '/^## Prompt/,/^## /{/^## /d;p;}' "$SCENARIO")

RESULTS=${DWH_EVAL_RESULTS:-$REPO/evals/results}
mkdir -p "$RESULTS"
BASE="$RESULTS/$NAME-$(git -C "$REPO" rev-parse --short "$REF")-$MODEL$SUFFIX"
OUTS=("$BASE.md")
if [ -n "$RUNS" ]; then
  OUTS=()
  for K in $(seq 1 "$RUNS"); do OUTS+=("$BASE-r$K.md"); done
fi
for OUT in "${OUTS[@]}"; do
  (cd "$WORK/repo" && printf '%s\n' "$PROMPT" \
    | claude -p --setting-sources project --model "$MODEL" --allowedTools "Read,Glob,Grep") > "$OUT"
  echo "wrote $OUT"
done
