#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PAPER_DIR="$ROOT_DIR/paper1"
RUN_DIR="$PAPER_DIR/data/runs"
mkdir -p "$RUN_DIR"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<EOF
Usage: scripts/run-gpt53-textmode-goldpass5-tail2.sh [stem]

Runs the two gold-pass easy5 tasks not covered by gpt53_textmode_goldpass2:
  sympy__sympy-13647,sympy__sympy-16988

Set BF_DRY_RUN=1 to print the command without calling the model.
EOF
  exit 0
fi

STEM="${1:-gpt53_textmode_goldpass5_tail2}"
LOG="$RUN_DIR/${STEM}.driver.log"
exec >> "$LOG" 2>&1

export BF_GPT_TEXT_MODE=1
export BF_T4_PROVIDER=gpt53_codex
export FORCE_COLOR=1
export HF_HOME="$PAPER_DIR/data/hf_cache"
export PYTHONPATH="$PAPER_DIR/src:$ROOT_DIR/external/mini-swe-agent/src"

PY="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

# The other three gold-pass easy5 tasks are already covered by
# gpt53_textmode_goldpass2. This tail run avoids reburning them.
IDS="sympy__sympy-13647,sympy__sympy-16988"

cd "$PAPER_DIR"

echo "[start] $(date -Is)"
echo "[stem] $STEM"
echo "[log] $LOG"
echo "[ids] $IDS"
echo "[policy] GPT-5.3 Codex text-mode ceiling tail; no GPT-5.5; jobs=1; resume enabled"

CMD=(
  timeout --signal=TERM --kill-after=45s 1800s
  "$PY" -u -m budgetflow.run_mini_swe_compare \
    --ids "$IDS" \
    --strategies all_gpt53 \
    --out-stem "$STEM" \
    --step-limit 80 \
    --heartbeat 30 \
    --jobs 1 \
    --trace-quiet \
    --trace-turns \
    --trace-max-turns 40 \
    --per-task-cap 1200 \
    --pressure-init 0.30 \
    --resume
)

if [[ "${BF_DRY_RUN:-0}" == "1" ]]; then
  printf '[dry-run]'
  printf ' %q' "${CMD[@]}"
  printf '\n'
  echo "[done] $(date -Is)"
  exit 0
fi

"${CMD[@]}"

"$PY" "$PAPER_DIR/scripts/summarize-nightly-budgetflow.py" "$STEM"
echo "[done] $(date -Is)"
