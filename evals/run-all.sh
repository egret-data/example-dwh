#!/usr/bin/env bash
# Run every scenario without and with skills at HEAD, grade each answer, then summarise.
#   evals/run-all.sh [--model <model>] [--runs N] [--scenario <name>]...
# --runs N runs the agent N times per scenario and side (answers <answer>-r1.md ... -rN.md) and grades each run;
# summary.py then decides each side by majority of its runs. --scenario limits the run to the named scenarios.
# Writes summary-<sha>.md to $DWH_EVAL_RESULTS (default evals/results). Each agent run and each judge call is a
# paid `claude -p` call: per scenario, 2 x N runs and 2 x N x DWH_EVAL_SAMPLES (default 3) judge calls.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
USAGE="usage: evals/run-all.sh [--model <model>] [--runs N] [--scenario <name>]..."
MODEL=sonnet
RUNS=
ONLY=()
while [ $# -gt 0 ]; do
  case $1 in
    --model) MODEL=${2:?--model needs a value}; shift 2 ;;
    --runs) RUNS=${2:?--runs needs a value}; shift 2 ;;
    --scenario) ONLY+=("${2:?--scenario needs a value}"); shift 2 ;;
    *) echo "unknown argument: $1" >&2; echo "$USAGE" >&2; exit 2 ;;
  esac
done
if [ -n "$RUNS" ] && ! [[ "$RUNS" =~ ^[1-9][0-9]*$ ]]; then
  echo "--runs takes a positive integer, got: $RUNS" >&2; exit 2
fi
RESULTS=${DWH_EVAL_RESULTS:-$REPO/evals/results}
SHA=$(git -C "$REPO" rev-parse --short HEAD)
SCENARIOS=()
if [ ${#ONLY[@]} -gt 0 ]; then
  for NAME in "${ONLY[@]}"; do SCENARIOS+=("$REPO/evals/scenarios/$NAME.md"); done
else
  SCENARIOS=("$REPO"/evals/scenarios/*.md)
fi
FAILED=0
for SCENARIO in "${SCENARIOS[@]}"; do
  NAME=$(basename "$SCENARIO" .md)
  for MODE in noskills skills; do
    FLAGS=(); SUFFIX=
    if [ "$MODE" = noskills ]; then FLAGS+=(--without-skills); SUFFIX=-noskills; fi
    BASE="$RESULTS/$NAME-$SHA-$MODEL$SUFFIX"
    ANSWERS=("$BASE.md")
    if [ -n "$RUNS" ]; then
      FLAGS+=(--runs "$RUNS")
      ANSWERS=()
      for K in $(seq 1 "$RUNS"); do ANSWERS+=("$BASE-r$K.md"); done
    fi
    if ! "$REPO/evals/run.sh" "$NAME" --model "$MODEL" ${FLAGS[@]+"${FLAGS[@]}"}; then
      echo "FAILED: $NAME ($MODE)" >&2
      FAILED=1
      continue
    fi
    for ANSWER in "${ANSWERS[@]}"; do
      python3 "$REPO/evals/grade.py" "$SCENARIO" "$ANSWER" || { echo "FAILED: $ANSWER" >&2; FAILED=1; }
    done
  done
done
python3 "$REPO/evals/summary.py" "$SHA"
exit "$FAILED"
