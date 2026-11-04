#!/usr/bin/env bash
# Run every scenario without and with skills at HEAD, grade each answer, then summarise.
#   evals/run-all.sh [--model <model>]
# Writes evals/results/summary-<sha>.md. Each run and each judge call is a paid `claude -p` call.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
MODEL=sonnet
if [ "${1:-}" = --model ]; then MODEL=${2:?--model needs a value}; fi
SHA=$(git -C "$REPO" rev-parse --short HEAD)
FAILED=0
for SCENARIO in "$REPO"/evals/scenarios/*.md; do
  NAME=$(basename "$SCENARIO" .md)
  for MODE in noskills skills; do
    FLAG=; SUFFIX=
    if [ "$MODE" = noskills ]; then FLAG=--without-skills; SUFFIX=-noskills; fi
    ANSWER="$REPO/evals/results/$NAME-$SHA-$MODEL$SUFFIX.md"
    if "$REPO/evals/run.sh" "$NAME" --model "$MODEL" $FLAG \
      && python3 "$REPO/evals/grade.py" "$SCENARIO" "$ANSWER"; then
      :
    else
      echo "FAILED: $NAME ($MODE)" >&2
      FAILED=1
    fi
  done
done
python3 "$REPO/evals/summary.py" "$SHA"
exit "$FAILED"
