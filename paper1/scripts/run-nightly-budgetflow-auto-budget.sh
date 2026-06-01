#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PAPER_DIR="$ROOT_DIR/paper1"
RUN_DIR="$PAPER_DIR/data/runs"
mkdir -p "$RUN_DIR"

MASTER_LOG="$RUN_DIR/nightly-budgetflow-auto-budget.log"
exec > >(tee -a "$MASTER_LOG") 2>&1

export FORCE_COLOR=1
export HF_HOME="$PAPER_DIR/data/hf_cache"
export PYTHONPATH="$PAPER_DIR/src:$ROOT_DIR/external/mini-swe-agent/src"

PY="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python"
fi

IDS="$("$PY" - <<'PY'
import json
from pathlib import Path
p = Path("paper1/data/gold_pass_easy5_instance_ids.json")
print(",".join(json.loads(p.read_text())["instance_ids"]))
PY
)"

cd "$PAPER_DIR"

echo "[start] $(date -Is)"
echo "[root] $ROOT_DIR"
echo "[log] $MASTER_LOG"
echo "[ids] $IDS"
echo "[policy] no docker; no gpt-5.5 in budgeted routing; qwen-only current pool"
echo

jsonl_count() {
  local file="$1"
  if [[ -f "$file" ]]; then
    wc -l < "$file" | tr -d ' '
  else
    echo 0
  fi
}

run_resume_loop() {
  local stem="$1"
  local expected="$2"
  local max_attempts="$3"
  local timeout_s="$4"
  shift 4

  local jsonl="$RUN_DIR/$stem.jsonl"
  local attempt=1
  while (( attempt <= max_attempts )); do
    local done
    done="$(jsonl_count "$jsonl")"
    echo "[loop] stem=$stem attempt=$attempt/$max_attempts done=$done/$expected timeout=${timeout_s}s"
    if (( done >= expected )); then
      echo "[ok] stem=$stem complete done=$done/$expected"
      return 0
    fi

    set +e
    timeout --signal=TERM --kill-after=45s "$timeout_s" "$@" --out-stem "$stem" --resume
    local code=$?
    set -e

    done="$(jsonl_count "$jsonl")"
    echo "[loop] stem=$stem exit=$code done=$done/$expected at $(date -Is)"
    if (( done >= expected )); then
      echo "[ok] stem=$stem complete after attempt=$attempt"
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

  echo "[warn] stem=$stem incomplete after $max_attempts attempts; leaving checkpoint for later resume"
  return 0
}

BASE_COMPARE=(
  "$PY" -u -m budgetflow.run_mini_swe_compare
  --step-limit 120
  --heartbeat 30
  --jobs 1
  --trace-quiet
  --trace-turns
  --trace-max-turns 80
  --per-task-cap 3000
  --pressure-init 0.30
)

echo "[phase 1] finish targeted rescue/stop-loss check"
run_resume_loop \
  "rescue_stoploss_targeted_v2" \
  4 \
  3 \
  900s \
  "${BASE_COMPARE[@]}" \
  --ids sympy__sympy-13647,sympy__sympy-16988 \
  --strategies stage_blind_tight,budgetflow_full_tight

echo
echo "[phase 2] easy5 automatic-budget main compare"
run_resume_loop \
  "budgetflow_goldpass5_autobudget_p030_v1" \
  15 \
  12 \
  1200s \
  "${BASE_COMPARE[@]}" \
  --ids "$IDS" \
  --strategies budget_only_tight,stage_blind_tight,budgetflow_full_tight

echo
echo "[phase 3] summarize latest results"
"$PY" - <<'PY'
import json
from collections import defaultdict
from pathlib import Path

run_dir = Path("data/runs")
for stem in ["rescue_stoploss_targeted_v2", "budgetflow_goldpass5_autobudget_p030_v1"]:
    path = run_dir / f"{stem}.jsonl"
    print(f"=== {stem} ===")
    if not path.exists():
        print("missing")
        continue
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    by = defaultdict(list)
    for row in rows:
        by[row["strategy"]].append(row)
    print(f"records={len(rows)}")
    for strategy, items in sorted(by.items()):
        passed = sum(1 for r in items if r.get("harness_resolved"))
        cost = sum(float(r.get("task_cost") or r.get("total_cost") or 0) for r in items)
        turns = sum(int(r.get("llm_turns") or 0) for r in items)
        failures = defaultdict(int)
        for r in items:
            if not r.get("harness_resolved"):
                failures[r.get("failure_class") or "unknown"] += 1
        fail_s = ",".join(f"{k}:{v}" for k, v in sorted(failures.items())) or "-"
        print(f"{strategy}: pass={passed}/{len(items)} cost={cost:.1f} turns={turns} fail={fail_s}")
    print()
PY

echo "[done] $(date -Is)"
