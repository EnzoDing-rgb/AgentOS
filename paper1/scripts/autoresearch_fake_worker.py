#!/usr/bin/env python3
"""Fake AutoResearch worker for no-paid smoke testing.

Reads a worker_prompt.md, writes a structured worker_output.md with fixed
sections. Does NOT modify src/, run API calls, or touch experiment data.

Usage:
  python3 scripts/autoresearch_fake_worker.py <prompt_path> <output_path>

Exit codes:
  0 — success (PASS injected into output)
  1 — usage error or missing paths
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

OUTPUT_TEMPLATE = """# AutoResearch Fake Worker Output

## Metadata

- **prompt_path:** {prompt_path}
- **output_path:** {output_path}
- **timestamp:** {timestamp}
- **exit_code:** 0

## Files Read

- {prompt_path}
- paper1/src/budgetflow/autoresearch_coordinator.py (metadata only)
- paper1/src/budgetflow/autoresearch_guard.py (metadata only)

## Commands Run

```
python3 -m pytest tests/test_autoresearch_coordinator.py -q --co 2>&1
python3 -c "print('fake smoke verification')"
```

## Artifacts Produced

- worker_output.md (this file)
- No src/ modifications
- No API calls made
- No experiment data changed

## Verification Summary

- All fake checks passed
- No real API consumption
- No Docker or harness invocation
- Workflow files on disk confirmed

## Result

AUTORESEARCH_FAKE_WORKER_RESULT:PASS
"""


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv

    if len(argv) != 3:
        print(f"Usage: {argv[0]} <prompt_path> <output_path>", file=sys.stderr)
        return 1

    prompt_path = Path(argv[1])
    output_path = Path(argv[2])

    if not prompt_path.is_file():
        print(f"prompt file not found: {prompt_path}", file=sys.stderr)
        return 1

    # Read the prompt (verify it exists and is readable).
    prompt_text = prompt_path.read_text()
    prompt_lines = len(prompt_text.strip().splitlines()) if prompt_text.strip() else 0
    print(f"[fake_worker] read prompt: {prompt_path} ({prompt_lines} lines)")

    # Ensure output directory exists.
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write structured output.
    output_text = OUTPUT_TEMPLATE.format(
        prompt_path=str(prompt_path),
        output_path=str(output_path),
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    output_path.write_text(output_text)
    print(f"[fake_worker] wrote output: {output_path} ({len(output_text)} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
