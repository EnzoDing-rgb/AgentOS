#!/usr/bin/env python3
"""Thin AutoResearch API worker — minimal Anthropic-compatible API call.

Bypasses claude -p session overhead by calling the Messages API directly.
Reads prompt + referenced docs, sends a compact request, writes output.

Usage:
  python3 scripts/autoresearch_api_worker.py <prompt_path> <output_path>

Environment (reads from current env, no hardcoded secrets):
  ANTHROPIC_BASE_URL  — e.g. https://api.deepseek.com/anthropic (required)
  ANTHROPIC_API_KEY   — x-api-key header value
  ANTHROPIC_AUTH_TOKEN — fallback if ANTHROPIC_API_KEY not set
  AUTORESEARCH_MODEL  — model name (default: ANTHROPIC_SMALL_FAST_MODEL or ANTHROPIC_MODEL)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# ── Helpers ──────────────────────────────────────────────────────────────────

def _mask(s: str, visible: int = 8) -> str:
    if len(s) <= visible:
        return s
    return s[:visible] + "..."

# ── Config from env ──────────────────────────────────────────────────────────

def _get_config() -> tuple[str, str, str]:
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "").rstrip("/")
    if not base_url:
        die("ANTHROPIC_BASE_URL not set")

    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or ""
    if not api_key:
        die("Neither ANTHROPIC_API_KEY nor ANTHROPIC_AUTH_TOKEN set")

    model = (
        os.environ.get("AUTORESEARCH_MODEL")
        or os.environ.get("ANTHROPIC_SMALL_FAST_MODEL")
        or os.environ.get("ANTHROPIC_MODEL")
        or ""
    )
    if not model:
        die("No model configured (set AUTORESEARCH_MODEL or ANTHROPIC_MODEL)")

    return base_url, api_key, model


def die(msg: str) -> None:
    print(f"[api_worker] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _write_metadata(
    output_path: Path,
    *,
    model: str,
    input_tokens: object,
    output_tokens: object,
    status_code: int,
    marker_in_output: bool,
    marker_appended: bool,
    error: str | None = None,
) -> Path:
    """Write worker_metadata.json sidecar alongside the output file."""
    meta = {
        "model": model,
        "input_tokens": input_tokens if isinstance(input_tokens, int) else 0,
        "output_tokens": output_tokens if isinstance(output_tokens, int) else 0,
        "status_code": status_code,
        "output_path": str(output_path),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "marker_present_in_model_output": marker_in_output,
        "marker_appended_by_wrapper": marker_appended,
        "error": error,
    }
    meta_path = output_path.parent / "worker_metadata.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    return meta_path


def _factual_header(model: str, input_tokens: object, output_tokens: object, meta_path: Path) -> str:
    """Script-factual header prepended to worker output."""
    return (
        f"<!-- AutoResearch API Worker — factual metadata\n"
        f"  model: {model}\n"
        f"  input_tokens: {input_tokens}\n"
        f"  output_tokens: {output_tokens}\n"
        f"  metadata: {meta_path.name}\n"
        f"-->\n\n"
    )


# ── Main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv

    # Parse optional flags before positional args.
    allow_wrapper_marker = "--allow-wrapper-marker" in argv
    positional = [a for a in argv[1:] if not a.startswith("--")]

    if len(positional) != 2:
        print(f"Usage: {argv[0]} [--allow-wrapper-marker] <prompt_path> <output_path>", file=sys.stderr)
        return 1

    prompt_path = Path(positional[0])
    output_path = Path(positional[1])

    if not prompt_path.is_file():
        print(f"[api_worker] prompt file not found: {prompt_path}", file=sys.stderr)
        return 1

    base_url, api_key, model = _get_config()

    # Read the worker prompt.
    prompt_text = prompt_path.read_text()
    print(f"[api_worker] read prompt: {prompt_path} ({len(prompt_text)} chars)")

    # Read the two docs referenced in the prompt.
    paper1_root = Path(__file__).resolve().parents[1]
    docs = {}
    for rel in ["docs/autoresearch_workflow.md", "docs/reports/036.md"]:
        doc_path = paper1_root / rel
        if doc_path.is_file():
            docs[rel] = doc_path.read_text()
            print(f"[api_worker] read doc: {rel} ({len(docs[rel])} chars)")
        else:
            print(f"[api_worker] WARNING: doc not found: {rel}", file=sys.stderr)

    # Build minimal system prompt.
    system_prompt = (
        "You are an AutoResearch Worker executing a bounded smoke task. "
        "Read the provided documents, write a concise structured worker_output.md. "
        "Output must include the marker AUTORESEARCH_REAL_API_SMOKE:PASS. "
        "Do NOT modify src/, tests/, or data/. No experiments or benchmarks. "
        "Output only the worker report markdown, no preamble."
    )

    # Build user message with prompt + docs.
    user_parts = [
        f"## Worker Prompt\n\n{prompt_text}",
    ]
    for rel, content in docs.items():
        user_parts.append(f"## {rel}\n\n{content}")
    user_message = "\n\n---\n\n".join(user_parts)

    # Call the API.
    url = f"{base_url}/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": 2048,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_message},
        ],
    }

    print(f"[api_worker] calling {url} model={model} key={_mask(api_key)}")

    try:
        import requests
        resp = requests.post(url, headers=headers, json=body, timeout=120)
    except Exception as exc:
        _write_metadata(output_path, model=model, input_tokens=0, output_tokens=0,
                        status_code=0, marker_in_output=False, marker_appended=False,
                        error=str(exc))
        print(f"[api_worker] ERROR: request failed: {exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        _write_metadata(output_path, model=model, input_tokens=0, output_tokens=0,
                        status_code=resp.status_code, marker_in_output=False, marker_appended=False,
                        error=f"HTTP {resp.status_code}: {resp.text[:300]}")
        print(f"[api_worker] ERROR: HTTP {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        return 1

    data = resp.json()

    # Extract usage if available.
    usage = data.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    print(f"[api_worker] response: input_tokens={input_tokens} output_tokens={output_tokens}")

    # Extract text content.
    content_blocks = data.get("content", [])
    text = ""
    for block in content_blocks:
        if block.get("type") == "text":
            text += block.get("text", "")

    if not text:
        _write_metadata(output_path, model=model, input_tokens=input_tokens,
                        output_tokens=output_tokens, status_code=resp.status_code,
                        marker_in_output=False, marker_appended=False,
                        error="no text content in response")
        print(f"[api_worker] ERROR: no text content in response", file=sys.stderr)
        return 1

    # Check marker. Default: do NOT append. Only append with --allow-wrapper-marker.
    marker_in_output = "AUTORESEARCH_REAL_API_SMOKE:PASS" in text
    marker_appended = False
    if not marker_in_output and allow_wrapper_marker:
        text += "\n\nAUTORESEARCH_REAL_API_SMOKE:PASS\n"
        marker_appended = True

    # Prepend factual header.
    meta_path = _write_metadata(
        output_path, model=model, input_tokens=input_tokens,
        output_tokens=output_tokens, status_code=resp.status_code,
        marker_in_output=marker_in_output, marker_appended=marker_appended,
    )
    header = _factual_header(model, input_tokens, output_tokens, meta_path)
    text = header + text

    # Write output.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text)
    print(f"[api_worker] wrote output: {output_path} ({len(text)} chars)")
    print(f"[api_worker] wrote metadata: {meta_path}")

    if not marker_in_output and not marker_appended:
        print(f"[api_worker] ERROR: marker not found in model output and wrapper marker disabled", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
