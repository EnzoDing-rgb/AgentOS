#!/usr/bin/env python3
"""AutoResearch worker dispatch — routes to fake or API worker based on prompt marker.

Reads the prompt file and checks for a dispatch marker comment:
  <!-- WORKER:fake -->  → use fake worker (no API, no cost)
  <!-- WORKER:api -->   → use thin API worker (real API call)

Default (no marker): API worker.

Usage:
  python3 scripts/autoresearch_worker_dispatch.py <prompt_path> <output_path>
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MARKER_FAKE = "<!-- WORKER:fake -->"
MARKER_API = "<!-- WORKER:api -->"

SCRIPTS = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv

    positional = [a for a in argv[1:] if not a.startswith("--")]

    if len(positional) != 2:
        print(f"Usage: {argv[0]} <prompt_path> <output_path>", file=sys.stderr)
        return 1

    prompt_path = Path(positional[0])
    output_path = Path(positional[1])

    if not prompt_path.is_file():
        print(f"[dispatch] prompt file not found: {prompt_path}", file=sys.stderr)
        return 1

    prompt_text = prompt_path.read_text()

    # Detect worker type from prompt marker.
    if MARKER_FAKE in prompt_text:
        worker = "fake"
        script = SCRIPTS / "autoresearch_fake_worker.py"
    elif MARKER_API in prompt_text:
        worker = "api"
        script = SCRIPTS / "autoresearch_api_worker.py"
    else:
        # Default to API worker.
        worker = "api"
        script = SCRIPTS / "autoresearch_api_worker.py"

    print(f"[dispatch] worker={worker} script={script}")

    result = subprocess.run(
        [sys.executable, str(script), str(prompt_path), str(output_path)],
        capture_output=True, text=True,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
