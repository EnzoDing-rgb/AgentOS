#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PAPER_DIR="$ROOT_DIR/paper1"
RUN_DIR="$PAPER_DIR/data/runs"
DOC_DIR="$PAPER_DIR/docs"
mkdir -p "$RUN_DIR" "$DOC_DIR" "$DOC_DIR/reports" "$DOC_DIR/blockers"

MASTER_LOG="$RUN_DIR/nightly-paper-progress.log"
exec >> "$MASTER_LOG" 2>&1

export FORCE_COLOR=1
export HF_HOME="$PAPER_DIR/data/hf_cache"
export PYTHONPATH="$PAPER_DIR/src:$ROOT_DIR/external/mini-swe-agent/src"

PY="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

cd "$PAPER_DIR"

refresh_table() {
  "$PY" scripts/build_paper_result_table.py \
    gpt53_textmode_goldpass2 \
    gpt53_textmode_goldpass5_tail2_foreground \
    gpt55_textmode_16988_ceiling \
    budgetflow_auto_v2_smoke \
    budgetflow_goldpass5_autobudget_p030_v1 \
    budgetflow_goldpass5_bounded_rescue_p030_v2 \
    rescue_stoploss_targeted_v2 \
    --label 'gpt53_textmode_goldpass2=raw ceiling GPT-5.3 goldpass2' \
    --label 'gpt53_textmode_goldpass5_tail2_foreground=raw ceiling GPT-5.3 tail2' \
    --label 'gpt55_textmode_16988_ceiling=raw ceiling GPT-5.5 hard case' \
    --label 'budgetflow_auto_v2_smoke=BudgetFlow auto v2 smoke' \
    --label 'budgetflow_goldpass5_autobudget_p030_v1=BudgetFlow autobudget p030' \
    --label 'budgetflow_goldpass5_bounded_rescue_p030_v2=BudgetFlow bounded rescue v2' \
    --label 'rescue_stoploss_targeted_v2=BudgetFlow rescue stoploss v2' \
    --out docs/reports/current_paper_result_table.md
}

write_blocker() {
  local code="$1"
  cat > docs/blockers/nightly_paper_progress_blocker.md <<EOF
# Nightly Paper Progress Blocker

Date: $(date -Is)

The night runner stopped before BudgetFlow compare because the Qwen provider preflight failed.

\`\`\`bash
PYTHONPATH=src:../external/mini-swe-agent/src ../.venv/bin/python -u -m budgetflow.run_deepseek_smoke --tier compare
\`\`\`

Exit code: \`$code\`

This is an infrastructure/auth blocker, not a BudgetFlow model result. Fix \`DASHSCOPE_API_KEY\`, then rerun:

\`\`\`bash
cd $PAPER_DIR
scripts/run-nightly-paper-progress.sh
\`\`\`

Log:

\`\`\`text
$MASTER_LOG
\`\`\`
EOF
}

echo "[start] $(date -Is)"
echo "[root] $ROOT_DIR"
echo "[log] $MASTER_LOG"
echo "[policy] no container engine; no ceiling model in budgeted routing; resume required"

echo "[phase 0] refresh current paper result table"
refresh_table

echo "[phase 1] provider preflight"
set +e
"$PY" -u -m budgetflow.run_deepseek_smoke --tier compare
preflight_code=$?
set -e
if (( preflight_code != 0 )); then
  echo "[blocker] qwen preflight failed exit=$preflight_code"
  write_blocker "$preflight_code"
  refresh_table
  echo "[done] stopped safely at $(date -Is)"
  exit 0
fi

echo "[phase 2] resumable goldpass5 automatic-budget compare"
scripts/run-auto-v2-goldpass5.sh budgetflow_goldpass5_auto_v2_p030_v1 --resume

echo "[phase 3] refresh current paper result table"
refresh_table

echo "[done] $(date -Is)"
