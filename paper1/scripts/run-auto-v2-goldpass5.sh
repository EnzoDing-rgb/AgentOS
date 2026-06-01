#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PAPER_DIR="$ROOT_DIR/paper1"
RUN_DIR="$PAPER_DIR/data/runs"
export PAPER_DIR
mkdir -p "$RUN_DIR"

STEM="${1:-budgetflow_goldpass5_auto_v2_p030_v1}"
MASTER_LOG="$RUN_DIR/${STEM}.driver.log"
exec >> "$MASTER_LOG" 2>&1

export FORCE_COLOR=1
export HF_HOME="$PAPER_DIR/data/hf_cache"
export PYTHONPATH="$PAPER_DIR/src:$ROOT_DIR/external/mini-swe-agent/src"

PY="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

IDS="$("$PY" - <<'PY'
import json
import os
from pathlib import Path

p = Path(os.environ["PAPER_DIR"]) / "data" / "gold_pass_easy5_instance_ids.json"
raw = json.loads(p.read_text())
print(",".join(raw["instance_ids"]))
PY
)"

cd "$PAPER_DIR"

echo "[start] $(date -Is)"
echo "[root] $ROOT_DIR"
echo "[stem] $STEM"
echo "[log] $MASTER_LOG"
echo "[ids] $IDS"
echo "[policy] no docker; no gpt-5.5 in budgeted routing; jobs=1; BF_T4_PROVIDER=${BF_T4_PROVIDER:-qwen}"
echo

jsonl_unique_count() {
  local file="$1"
  if [[ -f "$file" ]]; then
    "$PY" - "$file" <<'PY'
import json
import sys
from pathlib import Path

seen = set()
for line in Path(sys.argv[1]).read_text().splitlines():
    if not line.strip():
        continue
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        continue
    key = (row.get("strategy"), row.get("instance_id"))
    if all(key):
        seen.add(key)
print(len(seen))
PY
  else
    echo 0
  fi
}

run_resume_loop() {
  local expected=20
  local max_attempts=12
  local timeout_s=1200s
  local jsonl="$RUN_DIR/$STEM.jsonl"
  local attempt=1

  while (( attempt <= max_attempts )); do
    local done
    done="$(jsonl_unique_count "$jsonl")"
    echo "[loop] attempt=$attempt/$max_attempts done=$done/$expected timeout=${timeout_s}"
    if (( done >= expected )); then
      echo "[ok] complete done=$done/$expected"
      return 0
    fi

    set +e
    timeout --signal=TERM --kill-after=45s "$timeout_s" \
      "$PY" -u -m budgetflow.run_mini_swe_compare \
        --ids "$IDS" \
        --strategies budget_only_tight,stage_blind_tight,budgetflow_full_tight,budgetflow_auto_v2_tight \
        --out-stem "$STEM" \
        --step-limit 120 \
        --heartbeat 30 \
        --jobs 1 \
        --trace-quiet \
        --trace-turns \
        --trace-max-turns 60 \
        --per-task-cap 3000 \
        --pressure-init 0.30 \
        --resume
    local code=$?
    set -e

    done="$(jsonl_unique_count "$jsonl")"
    echo "[loop] exit=$code done=$done/$expected at $(date -Is)"
    if (( done >= expected )); then
      echo "[ok] complete after attempt=$attempt"
      return 0
    fi
    if [[ "$code" == "124" || "$code" == "137" || "$code" == "143" ]]; then
      echo "[warn] timeout/kill; resume next attempt"
    elif (( code != 0 )); then
      echo "[warn] nonzero exit; resume next attempt"
    fi
    attempt=$((attempt + 1))
    sleep 20
  done

  echo "[warn] incomplete after $max_attempts attempts; checkpoint left for resume"
  return 0
}

run_resume_loop
"$PY" "$PAPER_DIR/scripts/summarize-nightly-budgetflow.py" "$STEM"
echo "[done] $(date -Is)"
