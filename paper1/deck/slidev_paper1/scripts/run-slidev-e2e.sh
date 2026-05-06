#!/usr/bin/env bash
# Runs npm run build (unless SKIP_BUILD=1), then webapp-testing with_server.py + Slidev E2E.
# Requires: ~/.cursor/skills/webapp-testing or WEBAPP_TESTING_SKILL

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WEBAPP_TESTING_SKILL="${WEBAPP_TESTING_SKILL:-$HOME/.cursor/skills/webapp-testing}"
WITH_SERVER="$WEBAPP_TESTING_SKILL/scripts/with_server.py"

if [[ ! -f "$WITH_SERVER" ]]; then
  echo "FAIL: webapp-testing skill not found: $WITH_SERVER" >&2
  echo "Set WEBAPP_TESTING_SKILL to the directory containing scripts/with_server.py" >&2
  exit 127
fi

echo "Using with_server.py: $WITH_SERVER"

if [[ "${SKIP_BUILD:-}" != "1" ]]; then
  echo "Running npm run build..."
  npm run build
else
  echo "SKIP_BUILD=1 — skipping npm run build"
fi

exec python3 "$WITH_SERVER" \
  --server "cd \"$ROOT\" && npx slidev --port 3030" \
  --port 3030 \
  --timeout 120 \
  -- python3 "$ROOT/scripts/slidev_smoke.py"
