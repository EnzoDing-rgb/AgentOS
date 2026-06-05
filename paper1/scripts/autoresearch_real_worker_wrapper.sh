#!/bin/bash
# AutoResearch real Worker wrapper — invokes claude -p non-interactively.
#
# Usage: autosearch_real_worker_wrapper.sh <prompt_path> <output_path>
#
# Reads the prompt, calls claude -p with Read/Write tools allowed, captures
# stdout to the output path. The prompt instructs the Worker to write its
# structured output directly to the output path via the Write tool.
#
# Budget: hard cap at $0.30 per attempt.

set -euo pipefail

PROMPT_PATH="$1"
OUTPUT_PATH="$2"

if [ ! -f "$PROMPT_PATH" ]; then
    echo "ERROR: prompt file not found: $PROMPT_PATH" >&2
    exit 1
fi

# Ensure output dir exists.
mkdir -p "$(dirname "$OUTPUT_PATH")"

# Build a concise instruction that includes the output path target.
INSTRUCTION="Read $PROMPT_PATH. Follow it. Write output to $OUTPUT_PATH with marker AUTORESEARCH_REAL_API_SMOKE:PASS. Only Read + Write, no src/tests/data edits."

# Run claude non-interactively with tight budget, bare mode (minimal system prompt).
claude -p \
    --max-budget-usd 0.50 \
    --no-session-persistence \
    --bare \
    --allowedTools "Read,Write" \
    --output-format text \
    "$INSTRUCTION" 2>&1

echo "[wrapper] claude exit: $?"
