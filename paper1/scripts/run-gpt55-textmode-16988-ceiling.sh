#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PAPER_DIR="$ROOT_DIR/paper1"
RUN_DIR="$PAPER_DIR/data/runs"
mkdir -p "$RUN_DIR"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<EOF
Usage: scripts/run-gpt55-textmode-16988-ceiling.sh [stem]

Runs a single explicit GPT-5.5 ceiling probe on sympy__sympy-16988.
This is not part of normal BudgetFlow routing.

Set BF_DRY_RUN=1 to print the command without calling the model.
EOF
  exit 0
fi

child_pid=""
cleanup_child() {
  if [[ -n "$child_pid" ]]; then
    kill "$child_pid" 2>/dev/null || true
    wait "$child_pid" 2>/dev/null || true
  fi
}
trap 'cleanup_child; exit 143' TERM INT HUP

STEM="${1:-gpt55_textmode_16988_ceiling}"
LOG="$RUN_DIR/${STEM}.driver.log"
exec >> "$LOG" 2>&1

export BF_GPT_TEXT_MODE=1
export FORCE_COLOR=1
export HF_HOME="$PAPER_DIR/data/hf_cache"
export PYTHONPATH="$PAPER_DIR/src:$ROOT_DIR/external/mini-swe-agent/src"

PY="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

IDS="sympy__sympy-16988"

cd "$PAPER_DIR"

echo "[start] $(date -Is)"
echo "[stem] $STEM"
echo "[log] $LOG"
echo "[ids] $IDS"
echo "[policy] GPT-5.5 text-mode ceiling only; not budgeted routing; jobs=1; resume enabled"

CMD=(
  timeout --signal=TERM --kill-after=45s 1800s
  "$PY" -u -m budgetflow.run_mini_swe_compare
    --ids "$IDS"
    --strategies all_gpt55
    --out-stem "$STEM"
    --step-limit 80
    --heartbeat 30
    --jobs 1
    --trace-quiet
    --trace-turns
    --trace-max-turns 40
    --per-task-cap 1200
    --pressure-init 0.30
    --resume
)

if [[ "${BF_DRY_RUN:-0}" == "1" ]]; then
  printf '[dry-run]'
  printf ' %q' "${CMD[@]}"
  printf '\n'
  echo "[done] $(date -Is)"
  exit 0
fi

"${CMD[@]}" &
child_pid=$!
set +e
wait "$child_pid"
run_code=$?
set -e
child_pid=""
echo "[run] exit=$run_code"
if (( run_code != 0 )); then
  echo "[done] $(date -Is)"
  exit "$run_code"
fi

"$PY" "$PAPER_DIR/scripts/summarize-nightly-budgetflow.py" "$STEM"
echo "[done] $(date -Is)"
