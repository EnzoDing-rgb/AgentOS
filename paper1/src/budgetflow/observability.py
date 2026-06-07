"""Lightweight observability: harness evidence, heartbeat, record enrichment.

Keep changes minimal — parse what already exists in detail strings, don't
add new harness paths.
"""

from __future__ import annotations

import json
import os
import threading
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
    evaluated_complete: bool = False


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
    ev.evaluated_complete = all([
        ev.test_patch_ok,
        ev.fail_before_failed,
        ev.model_patch_ok,
        ev.pass_to_pass_ok,
        "fail_after=" in detail,
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


# ── Harness trust audit ──────────────────────────────────────────────────────

def build_harness_trust(record: dict) -> dict:
    """Audit harness trustworthiness per record.

    Returns {harness_trust, harness_issues, harness_owner, severity}.

    Trust levels:
      - trusted: evidence complete, submission patch, no gaps
      - trusted_fallback: evidence complete, but patch from worktree fallback (warn, not invalid)
      - suspicious: PASS with missing harness evidence (may still be correct)
      - invalid: PASS with blocking evidence gaps (fail_after/pass_to_pass missing)
      - incomplete: FAIL with no patch or incomplete evidence

    Severity:
      - none: no issue
      - warn: non-blocking gap (worktree fallback, missing test_patch)
      - blocking: evidence gap that makes the pass unreliable
    """
    issues: list[str] = []
    resolved = record.get("harness_resolved") in (True, "True", "true")

    # Re-parse evidence with record's detail
    evidence = parse_harness_evidence(str(record.get("detail") or ""))
    patch_extracted = bool(record.get("patch_extracted"))
    patch_source = str(record.get("patch_source") or "none")
    submitted_patch = record.get("submitted_patch") or ""
    agent_submitted = bool(record.get("agent_submitted"))
    agent_attempted = bool(record.get("agent_attempted_submit"))
    gold_edited = bool(record.get("agent_gold_edited"))
    gold_files = record.get("agent_gold_files") or []

    # Patch source audit
    if not patch_extracted:
        issues.append("no_patch_extracted")
    elif patch_source == "worktree":
        issues.append("patch_from_worktree_fallback")
    elif patch_source == "submission" and not submitted_patch:
        issues.append("submitted_patch_path_missing")
    elif patch_source not in ("submission", "worktree", "none"):
        issues.append(f"unknown_patch_source:{patch_source}")

    # Submission consistency
    if agent_submitted and not agent_attempted:
        issues.append("submitted_without_attempt")
    if agent_attempted and not agent_submitted:
        issues.append("attempted_but_not_submitted")

    # Harness evidence gaps
    if patch_extracted and not evidence.test_patch_ok:
        issues.append("test_patch_not_ok")
    if patch_extracted and not evidence.fail_before_failed:
        issues.append("fail_before_not_failed")
    if patch_extracted and not evidence.model_patch_ok:
        issues.append("model_patch_not_ok")
    if resolved and not evidence.fail_after_passed:
        issues.append("resolved_but_fail_after_not_passed")
    if resolved and not evidence.pass_to_pass_ok:
        issues.append("resolved_but_pass_to_pass_not_ok")

    # Gold file correspondence
    if gold_edited and not gold_files:
        issues.append("gold_edited_but_no_files_listed")

    # ── Determine trust level ──────────────────────────────────────────
    blocking_gaps = {"resolved_but_fail_after_not_passed", "resolved_but_pass_to_pass_not_ok"}
    issue_set = set(issues)

    if not patch_extracted and not resolved:
        trust = "incomplete"
    elif not evidence.evidence_complete:
        if resolved:
            if issue_set & blocking_gaps:
                trust = "invalid"  # PASS but fail_after/pass_to_pass missing
            else:
                trust = "suspicious"  # PASS but evidence incomplete, non-blocking
        elif evidence.evaluated_complete:
            trust = "trusted"  # evaluated patch failed cleanly
        else:
            trust = "incomplete"
    elif resolved and evidence.evidence_complete:
        if patch_source == "worktree":
            trust = "trusted_fallback"  # evidence ok, but patch from fallback
        elif issue_set:
            trust = "suspicious"
        else:
            trust = "trusted"
    elif not resolved and evidence.evidence_complete:
        trust = "trusted"  # properly failed with full evidence
    else:
        trust = "incomplete"

    # ── Determine severity ─────────────────────────────────────────────
    if not issues:
        severity = "none"
    elif issue_set & blocking_gaps:
        severity = "blocking"
    elif resolved and issue_set & {"fail_before_not_failed", "model_patch_not_ok"}:
        severity = "blocking"
    elif not resolved and patch_extracted and issue_set & {"fail_before_not_failed", "model_patch_not_ok"}:
        severity = "blocking"
    elif "patch_from_worktree_fallback" in issue_set and evidence.evidence_complete:
        severity = "warn"  # evidence says it's fine, just non-standard source
    elif "no_patch_extracted" in issue_set:
        severity = "blocking" if resolved else "warn"
    else:
        severity = "warn"

    owner = _harness_owner(issues, resolved, evidence, patch_extracted, gold_edited)

    return {
        "harness_trust": trust,
        "harness_issues": issues,
        "harness_owner": owner,
        "severity": severity,
    }


def _harness_owner(
    issues: list[str],
    resolved: bool,
    evidence: HarnessEvidence,
    patch_extracted: bool,
    gold_edited: bool,
) -> str:
    """Infer who owns the trust gap."""
    if not issues:
        return "none"
    harness_gaps = {"test_patch_not_ok", "fail_before_not_failed", "model_patch_not_ok",
                    "resolved_but_fail_after_not_passed", "resolved_but_pass_to_pass_not_ok"}
    model_gaps = {"submitted_without_attempt", "attempted_but_not_submitted",
                  "gold_edited_but_no_files_listed"}
    protocol_gaps = {"no_patch_extracted", "patch_from_worktree_fallback",
                     "submitted_patch_path_missing", "unknown_patch_source"}

    issue_set = set(issues)
    if issue_set & harness_gaps:
        return "harness"
    if issue_set & protocol_gaps:
        return "protocol"
    if issue_set & model_gaps:
        return "model"
    return "infra"


def audit_fallback_patch(record: dict) -> dict:
    """Audit relationship between submitted and fallback (worktree) patches.

    Returns:
        fallback_patch_exists: bool
        fallback_patch_lines: int | None
        submitted_patch_exists: bool
        submitted_vs_fallback: "same" | "different" | "no_submission" | "no_fallback" | "no_patch" | "unknown"
        fallback_audit: "clean" | "warn" | "blocking"
    """
    result = {
        "fallback_patch_exists": False,
        "fallback_patch_lines": None,
        "submitted_patch_exists": False,
        "submitted_vs_fallback": "unknown",
        "fallback_audit": "clean",
    }

    submitted_path = str(record.get("submitted_patch") or "")
    patch_source = str(record.get("patch_source") or "none")
    patch_extracted = bool(record.get("patch_extracted"))

    # Check submitted patch file
    if submitted_path:
        sp = Path(submitted_path)
        result["submitted_patch_exists"] = sp.is_file()

    # Check fallback (worktree) patch
    if patch_source == "worktree" and patch_extracted:
        result["fallback_patch_exists"] = True
        patch_text = str(record.get("patch_text") or "")
        if patch_text:
            result["fallback_patch_lines"] = len(patch_text.splitlines())
    elif patch_source == "submission" and patch_extracted:
        result["fallback_patch_exists"] = False

    # Compare
    if result["submitted_patch_exists"] and result["fallback_patch_exists"]:
        submitted_text = ""
        fallback_text = str(record.get("patch_text") or "")
        if submitted_path:
            try:
                submitted_text = Path(submitted_path).read_text()
            except Exception:
                pass
        if submitted_text and fallback_text:
            if submitted_text.strip() == fallback_text.strip():
                result["submitted_vs_fallback"] = "same"
            else:
                result["submitted_vs_fallback"] = "different"
                result["fallback_audit"] = "warn"
        else:
            result["submitted_vs_fallback"] = "unknown"
            result["fallback_audit"] = "warn"
    elif result["submitted_patch_exists"] and not result["fallback_patch_exists"]:
        result["submitted_vs_fallback"] = "no_fallback"
    elif not result["submitted_patch_exists"] and result["fallback_patch_exists"]:
        result["submitted_vs_fallback"] = "no_submission"
        result["fallback_audit"] = "warn"
    elif not result["submitted_patch_exists"] and not result["fallback_patch_exists"]:
        if patch_extracted:
            result["submitted_vs_fallback"] = "no_submission"
            result["fallback_audit"] = "blocking"
        else:
            result["submitted_vs_fallback"] = "no_patch"
            result["fallback_audit"] = "blocking"

    return result


def classify_incomplete_fail(record: dict) -> str:
    """Classify incomplete FAIL records into sub-categories.

    Returns:
        "no_patch_fail": model/protocol didn't produce a patch
        "harness_incomplete_fail": patch exists but harness evidence incomplete
        "expected_fail_incomplete": failure with sufficient evidence to know it didn't pass
        "not_applicable": record is PASS or not incomplete
    """
    if record.get("harness_resolved"):
        return "not_applicable"

    patch_extracted = bool(record.get("patch_extracted"))
    evidence = parse_harness_evidence(str(record.get("detail") or ""))
    trust = build_harness_trust(record)

    if not patch_extracted:
        return "no_patch_fail"

    # Explicit failure signals in harness detail → expected, not incomplete
    detail = str(record.get("detail") or "")
    if "fail_after=fail" in detail or "model_patch=fail" in detail:
        return "expected_fail_incomplete"

    if evidence.evidence_complete:
        return "expected_fail_incomplete"

    if trust["harness_trust"] == "incomplete":
        return "harness_incomplete_fail"

    return "harness_incomplete_fail"


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
            status="preparing",
            run_series=run_series,
        )
        self._lock = threading.Lock()
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
        elif active_strategy and active_instance and s.status == "preparing":
            s.status = "running"
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
        with self._lock:
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
            ident = threading.get_ident()
            tmp = self._path.with_name(f"{self._path.name}.{os.getpid()}.{ident}.tmp")
            tmp.write_text(json.dumps(data, indent=2) + "\n")
            os.replace(tmp, self._path)


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
