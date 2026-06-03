"""Lightweight observability: harness evidence, heartbeat, record enrichment.

Keep changes minimal — parse what already exists in detail strings, don't
add new harness paths.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path


# ── Harness evidence parsing ────────────────────────────────────────────────

@dataclass
class HarnessEvidence:
    test_patch_ok: bool = False
    fail_before_failed: bool = False
    model_patch_ok: bool = False
    fail_after_passed: bool = False
    pass_to_pass_ok: bool = False
    evidence_complete: bool = False


def parse_harness_evidence(detail: str) -> HarnessEvidence:
    """Parse SWE-bench detail string into structured evidence fields.

    Expected format (semicolon-separated key=value pairs):
      compat=...; test_patch=ok; fail_before=fail; model_patch=ok;
      fail_after=pass; pass_to_pass=pass

    Values are normalised: ok→True, pass→True, fail→True (the field describes
    the *expected* state, not success/failure).
    """
    ev = HarnessEvidence()
    if not detail:
        return ev
    parts = [p.strip() for p in detail.split(";")]
    fields: dict[str, str] = {}
    for part in parts:
        if "=" in part:
            k, v = part.split("=", 1)
            fields[k.strip()] = v.strip()

    ev.test_patch_ok = fields.get("test_patch") == "ok"
    ev.fail_before_failed = fields.get("fail_before") == "fail"
    ev.model_patch_ok = fields.get("model_patch") == "ok"
    ev.fail_after_passed = fields.get("fail_after") == "pass"
    ev.pass_to_pass_ok = fields.get("pass_to_pass") == "pass"

    ev.evidence_complete = all([
        ev.test_patch_ok,
        ev.fail_before_failed,
        ev.model_patch_ok,
        ev.fail_after_passed,
        ev.pass_to_pass_ok,
    ])
    return ev


def build_observability_status(record: dict) -> dict:
    """Compute observability_status from a record dict."""
    trace_count = int(record.get("turn_trace_count") or 0)
    trace_path = record.get("trace_steps") or record.get("submitted_patch") or ""
    submitted_patch = bool(record.get("submitted_patch"))
    harness_resolved = record.get("harness_resolved") in (True, "True", "true")

    evidence = parse_harness_evidence(str(record.get("detail") or ""))
    suspicious_pass = harness_resolved and not evidence.evidence_complete
    missing_evidence = []
    if not evidence.test_patch_ok:
        missing_evidence.append("test_patch_ok")
    if not evidence.fail_before_failed:
        missing_evidence.append("fail_before_failed")
    if not evidence.model_patch_ok:
        missing_evidence.append("model_patch_ok")
    if harness_resolved and not evidence.fail_after_passed:
        missing_evidence.append("fail_after_passed")
    if harness_resolved and not evidence.pass_to_pass_ok:
        missing_evidence.append("pass_to_pass_ok")

    return {
        "trace_available": trace_count > 0,
        "turn_trace_count": trace_count,
        "trace_steps_path": str(trace_path) if trace_path else None,
        "submitted_patch_exists": submitted_patch,
        "suspicious_pass": suspicious_pass,
        "missing_evidence": missing_evidence,
        "evidence_summary": _evidence_summary(evidence),
    }


def _evidence_summary(ev: HarnessEvidence) -> str:
    if ev.evidence_complete:
        return "complete"
    parts = []
    if not ev.test_patch_ok:
        parts.append("test_patch")
    if not ev.fail_before_failed:
        parts.append("fail_before")
    if not ev.model_patch_ok:
        parts.append("model_patch")
    if not ev.fail_after_passed:
        parts.append("fail_after")
    if not ev.pass_to_pass_ok:
        parts.append("pass_to_pass")
    return "missing:" + ",".join(parts) if parts else "complete"


# ── Heartbeat writer ─────────────────────────────────────────────────────────

@dataclass
class HeartbeatState:
    started_at: float = 0.0
    updated_at: float = 0.0
    total_expected: int = 0
    rows_done: int = 0
    active_strategy: str = ""
    active_instance: str = ""
    active_elapsed_s: float = 0.0
    last_completed: str = ""
    current_pid: int = 0
    status: str = "initializing"
    run_series: str = ""


class HeartbeatWriter:
    """Write a lightweight heartbeat file for long-running experiments."""

    def __init__(self, path: Path, run_series: str, total_expected: int):
        self._path = path
        self._state = HeartbeatState(
            started_at=time.time(),
            updated_at=time.time(),
            total_expected=total_expected,
            current_pid=os.getpid(),
            status="running",
            run_series=run_series,
        )
        self._write()

    def pulse(
        self,
        *,
        rows_done: int | None = None,
        active_strategy: str = "",
        active_instance: str = "",
        active_elapsed_s: float = 0.0,
        last_completed: str = "",
    ) -> None:
        s = self._state
        s.updated_at = time.time()
        if rows_done is not None:
            s.rows_done = rows_done
        if active_strategy:
            s.active_strategy = active_strategy
        if active_instance:
            s.active_instance = active_instance
        s.active_elapsed_s = active_elapsed_s
        if last_completed:
            s.last_completed = last_completed
        s.current_pid = os.getpid()
        if s.rows_done >= s.total_expected and s.total_expected > 0:
            s.status = "completed"
        self._write()

    def mark_done(self) -> None:
        self._state.status = "completed"
        self._state.updated_at = time.time()
        self._write()

    def mark_aborted(self, reason: str = "") -> None:
        self._state.status = f"aborted: {reason}" if reason else "aborted"
        self._state.updated_at = time.time()
        self._write()

    def _write(self) -> None:
        s = self._state
        data = {
            "started_at": s.started_at,
            "updated_at": s.updated_at,
            "total_expected": s.total_expected,
            "rows_done": s.rows_done,
            "active_strategy": s.active_strategy,
            "active_instance": s.active_instance,
            "active_elapsed_s": round(s.active_elapsed_s, 1),
            "last_completed": s.last_completed,
            "current_pid": s.current_pid,
            "status": s.status,
            "run_series": s.run_series,
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n")
        tmp.rename(self._path)


def load_heartbeat(path: Path) -> dict | None:
    """Read a heartbeat file, returning None if missing or stale."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def heartbeat_is_stale(hb: dict, stale_seconds: float = 600.0) -> bool:
    """Return True if heartbeat hasn't been updated in *stale_seconds*."""
    if not hb:
        return True
    updated = hb.get("updated_at", 0)
    return (time.time() - updated) > stale_seconds
