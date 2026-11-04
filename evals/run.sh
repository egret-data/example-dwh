#!/usr/bin/env bash
# Run one skill scenario headless with Claude Code (spec §8.2) and save the answer for grading.
#   evals/run.sh <scenario> [--ref <git-ref>] [--model <model>]
# --ref defaults to HEAD; use the plan's base commit for a RED (no-skills) baseline.
# The run sees the repository at <ref>, plus the scenario's fixture copied over it, with read-only tools.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
NAME=${1:?usage: evals/run.sh <scenario> [--ref <git-ref>] [--model <model>]}
shift
REF=HEAD
MODEL=sonnet
while [ $# -gt 0 ]; do
  case $1 in
    --ref) REF=$2; shift 2 ;;
    --model) MODEL=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
SCENARIO="$REPO/evals/scenarios/$NAME.md"
[ -f "$SCENARIO" ] || { echo "no scenario $SCENARIO" >&2; exit 2; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/dwh-eval.XXXXXX")"
git -C "$REPO" worktree add --detach --quiet "$WORK/repo" "$REF"
trap 'git -C "$REPO" worktree remove --force "$WORK/repo"' EXIT

FIXTURE=$(sed -n 's/^fixture: *//p' "$SCENARIO" | head -1)
if [ -n "$FIXTURE" ]; then
  python3 -c 'import shutil, sys; shutil.copytree(sys.argv[1], sys.argv[2], dirs_exist_ok=True)' \
    "$REPO/evals/fixtures/$FIXTURE" "$WORK/repo"
fi
# The agent must not read its own grading rubric or the skill texts in the plans and verification records.
git -C "$WORK/repo" rm -r -q --ignore-unmatch evals docs/en/plans docs/en/verification
# Commit the fixture and the removal in the throwaway worktree so the agent sees a clean tree.
git -C "$WORK/repo" add -A
git -C "$WORK/repo" diff --cached --quiet \
  || git -C "$WORK/repo" -c user.name=dwh-eval -c user.email=dwh-eval@example.invalid \
    commit --quiet --no-verify -m "eval fixture: ${FIXTURE:-none}"
PROMPT=$(sed -n '/^## Prompt/,/^## /{/^## /d;p;}' "$SCENARIO")

mkdir -p "$REPO/evals/results"
OUT="$REPO/evals/results/$NAME-$(git -C "$REPO" rev-parse --short "$REF")-$MODEL.md"
(cd "$WORK/repo" && printf '%s\n' "$PROMPT" \
  | claude -p --setting-sources project --model "$MODEL" --allowedTools "Read,Glob,Grep") > "$OUT"
echo "wrote $OUT"
