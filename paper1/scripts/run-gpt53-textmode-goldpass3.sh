#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PAPER_DIR="$ROOT_DIR/paper1"
RUN_DIR="$PAPER_DIR/data/runs"
mkdir -p "$RUN_DIR"

STEM="${1:-gpt53_textmode_goldpass3}"
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

IDS="sympy__sympy-13480,sympy__sympy-17139,sympy__sympy-20212"

cd "$PAPER_DIR"

echo "[start] $(date -Is)"
echo "[stem] $STEM"
echo "[log] $LOG"
echo "[ids] $IDS"
echo "[policy] GPT-5.3 Codex text-mode ceiling; no GPT-5.5; jobs=1; resume enabled"

timeout --signal=TERM --kill-after=45s 1800s \
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

"$PY" "$PAPER_DIR/scripts/summarize-nightly-budgetflow.py" "$STEM"
echo "[done] $(date -Is)"
