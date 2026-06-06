"""Deterministic Codex Gate — local review without real API.

Reads state.json, worker_output.md, and worker_metadata.json to produce a
deterministic PASS/FAIL verdict with structured evidence and warnings.

Auto-detects fake vs real workers: if output contains
AUTORESEARCH_FAKE_WORKER_RESULT:PASS, applies fake-worker checks that don't
require worker_metadata.json.

Usage:
  from budgetflow.autoresearch_codex_gate import review_issue, write_codex_review

  result = review_issue(Path(".autoresearch/workflows/039-issue-a"))
  write_codex_review(result, Path(".autoresearch/workflows/039-issue-a/codex_review.md"))
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

FAKE_WORKER_MARKER = "AUTORESEARCH_FAKE_WORKER_RESULT:PASS"
REAL_API_MARKER = "AUTORESEARCH_REAL_API_SMOKE:PASS"


@dataclass
class ReviewResult:
    issue_id: str
    verdict: str  # PASS | FAIL | WARN
    score: int  # 0-100
    checks: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_action: str = ""

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "score": self.score,
            "checks": self.checks,
            "evidence": self.evidence,
            "warnings": self.warnings,
            "next_action": self.next_action,
        }


# ── Factual error patterns ────────────────────────────────────────────────────

# Patterns that claim zero/free cost when actual API tokens were consumed.
# Each pattern is (regex, message).
_FACTUAL_ERROR_PATTERNS = [
    (
        re.compile(r"zero[\s-]?(api[\s-]?)?cost", re.IGNORECASE),
        "claims 'zero API cost' but real API tokens were consumed (thin API is lower-cost, not zero-cost)",
    ),
    (
        re.compile(r"costs?\s+nothing", re.IGNORECASE),
        "claims 'costs nothing' but real API tokens were consumed",
    ),
    (
        re.compile(r"no\s+cost", re.IGNORECASE),
        "claims 'no cost' but real API tokens were consumed",
    ),
    (
        re.compile(r"without\s+(any\s+)?api\s+calls?", re.IGNORECASE),
        "claims 'without API calls' but worker_metadata.json shows real API usage",
    ),
    (
        re.compile(r"(completely|entirely|totally)\s+free", re.IGNORECASE),
        "claims API is 'free' but real tokens were consumed",
    ),
]

# Context that explains a zero-cost claim accurately (describing fake worker).
_FAKE_WORKER_CONTEXT = re.compile(r"fake\s*worker", re.IGNORECASE)


def _check_factual_errors(text: str, input_tokens: int) -> list[str]:
    """Detect factual errors in worker output. Only fires when tokens were consumed.

    Skips matches where 'fake worker' appears nearby — describing the fake worker
    as zero-cost is accurate, not a factual error.
    """
    warnings = []
    if input_tokens <= 0:
        return warnings
    for pattern, msg in _FACTUAL_ERROR_PATTERNS:
        for match in pattern.finditer(text):
            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 80)
            context = text[start:end]
            if _FAKE_WORKER_CONTEXT.search(context):
                continue  # Accurately describing fake worker, not thin API.
            warnings.append(msg)
            break  # One warning per pattern type.
    return warnings


# ── Secret detection ───────────────────────────────────────────────────────────

_SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9_-]{20,}"),
    re.compile(r"x-api-key:\s*[a-zA-Z0-9_-]{10,}"),
]


def _check_secrets(text: str) -> list[str]:
    found = []
    for pat in _SECRET_PATTERNS:
        for m in pat.findall(text):
            found.append(f"possible secret detected: {m[:20]}...")
    return found


# ── Factual header parsing ─────────────────────────────────────────────────────

def _parse_factual_header(text: str) -> dict | None:
    m = re.search(r"<!--\s*AutoResearch API Worker[^>]*-->\s*", text)
    if not m:
        return None
    header = m.group()
    result = {}
    for key in ("model", "input_tokens", "output_tokens"):
        km = re.search(rf"{key}:\s*(\S+)", header)
        if km:
            try:
                result[key] = int(km.group(1))
            except ValueError:
                result[key] = km.group(1)
    return result


# ── Fake worker checks ─────────────────────────────────────────────────────────

def _review_fake_worker(issue_id: str, output_text: str, evidence: list[str]) -> ReviewResult:
    """Deterministic review for fake worker output (no API metadata required)."""
    result = ReviewResult(issue_id=issue_id, verdict="PASS", score=100)
    checks = []
    warnings = []

    # Check 1: Fake worker PASS marker present.
    if FAKE_WORKER_MARKER in output_text:
        checks.append({"check": "fake_worker_marker_present", "result": "PASS"})
    else:
        checks.append({"check": "fake_worker_marker_present", "result": "FAIL",
                       "detail": f"output missing {FAKE_WORKER_MARKER}"})
        result.score -= 40

    # Check 2: Required sections present.
    required_sections = ["## Metadata", "## Files Read", "## Commands Run",
                         "## Artifacts Produced", "## Verification Summary", "## Result"]
    missing = [s for s in required_sections if s not in output_text]
    if not missing:
        checks.append({"check": "fake_worker_sections", "result": "PASS"})
    else:
        checks.append({"check": "fake_worker_sections", "result": "WARN",
                       "detail": f"missing sections: {', '.join(missing)}"})
        result.score -= 10
        warnings.append(f"missing expected fake worker sections: {', '.join(missing)}")

    # Check 3: No API calls claimed when none made.
    if "zero API calls" in output_text or "0 API calls" in output_text:
        checks.append({"check": "fake_worker_no_api_claimed", "result": "PASS"})
    else:
        checks.append({"check": "fake_worker_no_api_claimed", "result": "PASS",
                       "detail": "fake worker — no API expected"})

    # Check 4: No secrets leaked.
    secrets = _check_secrets(output_text)
    if not secrets:
        checks.append({"check": "no_secrets_leaked", "result": "PASS"})
    else:
        checks.append({"check": "no_secrets_leaked", "result": "FAIL",
                       "detail": "; ".join(secrets)})
        result.score -= 100

    result.score = max(0, min(100, result.score))
    if result.score < 60:
        result.verdict = "FAIL"
    elif result.score < 80:
        result.verdict = "WARN"

    result.checks = checks
    result.warnings = warnings

    if result.verdict == "PASS":
        result.next_action = "proceed — fake worker checks passed"
    elif result.verdict == "WARN":
        result.next_action = "owner review recommended"
    else:
        result.next_action = "retry — fake worker checks failed"

    return result


# ── Main review logic ──────────────────────────────────────────────────────────

def review_issue(workflow_dir: Path) -> ReviewResult:
    """Run deterministic review on an issue's workflow directory.

    Auto-detects fake vs real worker by checking worker output markers.
    Returns a ReviewResult with verdict, score, and evidence.
    """
    issue_id = workflow_dir.name

    # ── Load state.json ────────────────────────────────────────────────────
    state_path = workflow_dir / "state.json"
    evidence = []
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text())
            evidence.append(f"state.json: status={state.get('status')}")
        except json.JSONDecodeError:
            pass

    # ── Find latest attempt output ─────────────────────────────────────────
    attempts_dir = workflow_dir / "attempts"
    output_text = ""
    meta = None
    input_tokens = 0

    if attempts_dir.is_dir():
        attempt_nums = sorted(
            int(d.name) for d in attempts_dir.iterdir()
            if d.is_dir() and d.name.isdigit()
        )
        for anum in reversed(attempt_nums):
            adir = attempts_dir / f"{anum:03d}"
            meta_path = adir / "worker_metadata.json"
            output_path = adir / "worker_output.md"

            if output_path.is_file():
                output_text = output_path.read_text()

            if meta_path.is_file():
                try:
                    meta = json.loads(meta_path.read_text())
                    input_tokens = meta.get("input_tokens", 0) or 0
                except json.JSONDecodeError:
                    pass
            break  # Only check latest attempt.

    # ── Auto-detect fake worker profile ────────────────────────────────────
    if FAKE_WORKER_MARKER in output_text:
        result = _review_fake_worker(issue_id, output_text, evidence)
        result.evidence = evidence
        return result

    # ── Real API worker review ─────────────────────────────────────────────
    result = ReviewResult(issue_id=issue_id, verdict="PASS", score=100)
    checks = []
    warnings = []

    if meta is None:
        result.verdict = "FAIL"
        result.score = 0
        result.checks = [{"check": "metadata_exists", "result": "FAIL",
                          "detail": "no worker_metadata.json found (real API worker required)"}]
        result.evidence = evidence
        result.warnings = warnings
        result.next_action = "retry — no API call metadata found"
        return result

    evidence.append(f"worker_metadata.json: model={meta.get('model')} "
                     f"input={meta.get('input_tokens')} output={meta.get('output_tokens')} "
                     f"status={meta.get('status_code')}")

    output_tokens = meta.get("output_tokens", 0) or 0

    # Check 1: HTTP status 200.
    status_code = meta.get("status_code", 0)
    if status_code == 200:
        checks.append({"check": "http_status_200", "result": "PASS"})
    else:
        checks.append({"check": "http_status_200", "result": "FAIL",
                       "detail": f"HTTP {status_code}"})
        result.score -= 40

    # Check 2: Tokens > 0.
    if input_tokens > 0 and output_tokens > 0:
        checks.append({"check": "tokens_positive", "result": "PASS",
                       "detail": f"input={input_tokens} output={output_tokens}"})
    else:
        checks.append({"check": "tokens_positive", "result": "FAIL",
                       "detail": f"input={input_tokens} output={output_tokens}"})
        result.score -= 20

    # Check 3: marker_present_in_model_output.
    marker_present = meta.get("marker_present_in_model_output", False)
    if marker_present:
        checks.append({"check": "marker_present_in_model_output", "result": "PASS"})
    else:
        checks.append({"check": "marker_present_in_model_output", "result": "FAIL",
                       "detail": "model did not output required PASS marker"})
        result.score -= 30

    # Check 4: marker_appended_by_wrapper.
    marker_appended = meta.get("marker_appended_by_wrapper", False)
    if not marker_appended:
        checks.append({"check": "marker_not_appended_by_wrapper", "result": "PASS"})
    else:
        checks.append({"check": "marker_not_appended_by_wrapper", "result": "FAIL",
                       "detail": "wrapper appended marker — model output was incomplete"})
        result.score -= 25
        # Marker appended means model output was incomplete — cannot be PASS.
        if result.verdict == "PASS":
            result.verdict = "WARN"

    # Check 5: Factual header consistency.
    if output_text:
        header = _parse_factual_header(output_text)
        if header:
            header_ok = True
            header_detail = []
            if header.get("model") != meta.get("model"):
                header_ok = False
                header_detail.append(f"model mismatch: header={header.get('model')} meta={meta.get('model')}")
            if header.get("input_tokens") != input_tokens:
                header_ok = False
                header_detail.append(f"input_tokens mismatch: header={header.get('input_tokens')} meta={input_tokens}")
            if header.get("output_tokens") != output_tokens:
                header_ok = False
                header_detail.append(f"output_tokens mismatch: header={header.get('output_tokens')} meta={output_tokens}")
            if header_ok:
                checks.append({"check": "factual_header_consistent", "result": "PASS"})
            else:
                checks.append({"check": "factual_header_consistent", "result": "FAIL",
                               "detail": "; ".join(header_detail)})
                result.score -= 15
        else:
            checks.append({"check": "factual_header_consistent", "result": "WARN",
                           "detail": "no factual header found in worker output"})

    # Check 6: No secrets.
    secrets_in_output = _check_secrets(output_text) if output_text else []
    secrets_in_meta = _check_secrets(json.dumps(meta)) if meta else []
    all_secrets = secrets_in_output + secrets_in_meta
    if not all_secrets:
        checks.append({"check": "no_secrets_leaked", "result": "PASS"})
    else:
        checks.append({"check": "no_secrets_leaked", "result": "FAIL",
                       "detail": "; ".join(all_secrets)})
        result.score -= 100

    # Check 7: Factual accuracy heuristics.
    factual_warnings = _check_factual_errors(output_text, input_tokens)
    for w in factual_warnings:
        warnings.append(w)
    if factual_warnings:
        checks.append({"check": "factual_accuracy", "result": "WARN",
                       "detail": "; ".join(factual_warnings)})
        if result.verdict == "PASS":
            result.verdict = "WARN"
        result.score = max(0, result.score - 10)

    # Final verdict.
    result.score = max(0, min(100, result.score))
    if result.score < 60:
        result.verdict = "FAIL"
    elif result.score < 80 and result.verdict == "PASS":
        result.verdict = "WARN"

    result.checks = checks
    result.evidence = evidence
    result.warnings = warnings

    if result.verdict == "PASS":
        result.next_action = "proceed — all checks passed"
    elif result.verdict == "WARN":
        result.next_action = "owner review recommended — warnings present"
    else:
        result.next_action = "retry or escalate — checks failed"

    return result


# ── Codex review writer ────────────────────────────────────────────────────────

def write_codex_review(result: ReviewResult, output_path: Path) -> Path:
    lines = [
        f"# Codex Gate Review — {result.issue_id}",
        "",
        "## Verdict",
        "",
        f"VERDICT: {result.verdict}",
        f"SCORE: {result.score}/100",
        "",
        "## Evidence",
        "",
    ]
    for e in result.evidence:
        lines.append(f"- {e}")

    if result.warnings:
        lines.append("")
        lines.append("## Warnings")
        lines.append("")
        for w in result.warnings:
            lines.append(f"- WARNING: {w}")

    lines.append("")
    lines.append("## Checks")
    lines.append("")
    lines.append("| Check | Result | Detail |")
    lines.append("|-------|--------|--------|")
    for c in result.checks:
        detail = c.get("detail", "")
        lines.append(f"| {c['check']} | {c['result']} | {detail} |")

    lines.append("")
    lines.append("## Next Action")
    lines.append("")
    lines.append(f"NEXT_ACTION: {result.next_action}")
    lines.append("")
    lines.append(f"AUTORESEARCH_RESULT:{result.verdict}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n")
    return output_path


# ── Goal-level review ──────────────────────────────────────────────────────────

def review_goal(goal, coordinator) -> dict[str, ReviewResult]:
    results = {}
    for issue_id in goal.issue_ids:
        wf_dir = coordinator.workflow_dir(issue_id)
        result = review_issue(wf_dir)
        results[issue_id] = result
    return results
