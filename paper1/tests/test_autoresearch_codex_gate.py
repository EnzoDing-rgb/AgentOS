"""Tests for deterministic Codex gate — review_issue, write_codex_review, review_goal."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from budgetflow.autoresearch_codex_gate import (  # noqa: E402
    ReviewResult,
    _check_factual_errors,
    _check_secrets,
    _parse_factual_header,
    review_issue,
    write_codex_review,
)
from budgetflow.autoresearch_coordinator import AutoResearchCoordinator  # noqa: E402


@pytest.fixture
def paper1_tmp(tmp_path):
    p1 = tmp_path / "paper1"
    p1.mkdir()
    (p1 / "src").mkdir()
    (p1 / "tests").mkdir()
    (p1 / "docs").mkdir()
    return p1


@pytest.fixture
def coordinator(paper1_tmp):
    return AutoResearchCoordinator(paper1_root=paper1_tmp)


def _make_workflow_with_metadata(coordinator, issue_id: str, meta: dict, output_text: str = ""):
    """Create a workflow with an attempt that has worker_metadata.json and worker_output.md."""
    state = coordinator.create_workflow(issue_id, "# Test prompt\n")
    state.attempt = 1
    coordinator._write_state(state)

    adir = coordinator.attempt_dir(issue_id, 1)
    adir.mkdir(parents=True, exist_ok=True)

    if output_text:
        out = adir / "worker_output.md"
        out.write_text(output_text)

    meta_path = adir / "worker_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    return coordinator.workflow_dir(issue_id)


# ── Factual error detection ───────────────────────────────────────────────────

class TestFactualErrors:
    def test_zero_cost_with_tokens_triggers_warning(self):
        warnings = _check_factual_errors("This approach is zero-cost.", input_tokens=100)
        assert len(warnings) >= 1
        assert any("zero" in w.lower() for w in warnings)

    def test_zero_cost_without_tokens_no_warning(self):
        warnings = _check_factual_errors("This approach is zero-cost.", input_tokens=0)
        assert len(warnings) == 0

    def test_costs_nothing_triggers(self):
        warnings = _check_factual_errors("The thin worker costs nothing.", input_tokens=50)
        assert len(warnings) >= 1

    def test_normal_text_no_false_positive(self):
        warnings = _check_factual_errors(
            "The thin API worker costs approximately $0.001 per call.", input_tokens=100
        )
        assert len(warnings) == 0


# ── Secret detection ──────────────────────────────────────────────────────────

class TestSecretDetection:
    def test_sk_key_detected(self):
        secrets = _check_secrets("Using key: sk-this-is-a-very-long-test-key-1234")
        assert len(secrets) >= 1

    def test_no_secrets_in_normal_text(self):
        secrets = _check_secrets("The API worker used model deepseek-v4-flash.")
        assert len(secrets) == 0

    def test_x_api_key_header_detected(self):
        secrets = _check_secrets('headers = {"x-api-key": "sk-abcdefghijklmnopqrstuv"}')
        assert len(secrets) >= 1


# ── Header parsing ────────────────────────────────────────────────────────────

class TestHeaderParsing:
    def test_parse_valid_header(self):
        header = """<!-- AutoResearch API Worker — factual metadata
  model: deepseek-v4-flash
  input_tokens: 4887
  output_tokens: 808
  metadata: worker_metadata.json
-->"""
        result = _parse_factual_header(header)
        assert result is not None
        assert result["model"] == "deepseek-v4-flash"
        assert result["input_tokens"] == 4887
        assert result["output_tokens"] == 808

    def test_no_header_returns_none(self):
        result = _parse_factual_header("# Just a normal markdown file\n\nContent.")
        assert result is None


# ── Review logic ──────────────────────────────────────────────────────────────

class TestReviewIssue:
    def test_pass_with_valid_metadata(self, coordinator):
        wf_dir = _make_workflow_with_metadata(coordinator, "test-pass", {
            "model": "deepseek-v4-flash",
            "input_tokens": 500,
            "output_tokens": 100,
            "status_code": 200,
            "marker_present_in_model_output": True,
            "marker_appended_by_wrapper": False,
            "error": None,
            "timestamp_utc": "2026-06-05T00:00:00Z",
            "output_path": "/tmp/out.md",
        }, output_text="""<!-- AutoResearch API Worker — factual metadata
  model: deepseek-v4-flash
  input_tokens: 500
  output_tokens: 100
  metadata: worker_metadata.json
-->
# Report
AUTORESEARCH_REAL_API_SMOKE:PASS
""")
        result = review_issue(wf_dir)
        assert result.verdict == "PASS"
        assert result.score == 100

    def test_fail_without_metadata(self, coordinator):
        state = coordinator.create_workflow("test-no-meta", "# Test\n")
        wf_dir = coordinator.workflow_dir("test-no-meta")
        result = review_issue(wf_dir)
        assert result.verdict == "FAIL"
        assert result.score == 0

    def test_fail_on_http_error(self, coordinator):
        wf_dir = _make_workflow_with_metadata(coordinator, "test-http-err", {
            "model": "deepseek-v4-flash",
            "input_tokens": 0,
            "output_tokens": 0,
            "status_code": 500,
            "marker_present_in_model_output": False,
            "marker_appended_by_wrapper": False,
            "error": "HTTP 500: Internal Server Error",
        })
        result = review_issue(wf_dir)
        assert result.verdict == "FAIL"
        assert result.score < 60

    def test_warn_on_factual_error(self, coordinator):
        wf_dir = _make_workflow_with_metadata(coordinator, "test-fact-err", {
            "model": "deepseek-v4-flash",
            "input_tokens": 400,
            "output_tokens": 80,
            "status_code": 200,
            "marker_present_in_model_output": True,
            "marker_appended_by_wrapper": False,
            "error": None,
        }, output_text="""<!-- AutoResearch API Worker — factual metadata
  model: deepseek-v4-flash
  input_tokens: 400
  output_tokens: 80
  metadata: worker_metadata.json
-->
# Report
The thin worker is a zero-cost alternative.
AUTORESEARCH_REAL_API_SMOKE:PASS
""")
        result = review_issue(wf_dir)
        assert result.verdict in ("WARN", "FAIL")
        assert len(result.warnings) >= 1
        assert any("zero" in w.lower() for w in result.warnings)

    def test_fail_on_marker_appended(self, coordinator):
        wf_dir = _make_workflow_with_metadata(coordinator, "test-marker-app", {
            "model": "deepseek-v4-flash",
            "input_tokens": 400,
            "output_tokens": 80,
            "status_code": 200,
            "marker_present_in_model_output": False,
            "marker_appended_by_wrapper": True,
            "error": None,
        }, output_text="# Report\nAUTORESEARCH_REAL_API_SMOKE:PASS")
        result = review_issue(wf_dir)
        # marker_appended_by_wrapper=True should reduce score substantially
        assert result.score < 100

    def test_header_mismatch_detected(self, coordinator):
        wf_dir = _make_workflow_with_metadata(coordinator, "test-header-mismatch", {
            "model": "deepseek-v4-flash",
            "input_tokens": 500,
            "output_tokens": 100,
            "status_code": 200,
            "marker_present_in_model_output": True,
            "marker_appended_by_wrapper": False,
            "error": None,
        }, output_text="""<!-- AutoResearch API Worker — factual metadata
  model: deepseek-v4-flash
  input_tokens: 999
  output_tokens: 100
  metadata: worker_metadata.json
-->
# Report
AUTORESEARCH_REAL_API_SMOKE:PASS
""")
        result = review_issue(wf_dir)
        # Header says 999 input tokens, metadata says 500 — mismatch
        assert result.score < 100
        header_check = [c for c in result.checks if c["check"] == "factual_header_consistent"]
        assert len(header_check) == 1
        assert header_check[0]["result"] == "FAIL"

    def test_secret_leak_fail(self, coordinator):
        wf_dir = _make_workflow_with_metadata(coordinator, "test-secret", {
            "model": "deepseek-v4-flash",
            "input_tokens": 100,
            "output_tokens": 50,
            "status_code": 200,
            "marker_present_in_model_output": True,
            "marker_appended_by_wrapper": False,
            "error": None,
        }, output_text="My key is sk-this-is-a-very-long-secret-key-leak")
        result = review_issue(wf_dir)
        assert result.verdict == "FAIL"
        assert result.score == 0  # Secret leak is automatic fail

    def test_zero_tokens_fail(self, coordinator):
        wf_dir = _make_workflow_with_metadata(coordinator, "test-zero-tok", {
            "model": "deepseek-v4-flash",
            "input_tokens": 0,
            "output_tokens": 0,
            "status_code": 200,
            "marker_present_in_model_output": True,
            "marker_appended_by_wrapper": False,
            "error": None,
        })
        result = review_issue(wf_dir)
        assert result.score <= 80  # Should be penalized for zero tokens


# ── Fake worker profile ───────────────────────────────────────────────────────

class TestFakeWorkerProfile:
    def test_fake_worker_auto_detect_pass(self, coordinator):
        """Fake worker output with marker should auto-detect and PASS."""
        wf_dir = _make_workflow_with_metadata(coordinator, "test-fake-pass", {
            "model": "fake",
            "input_tokens": 0,
            "output_tokens": 0,
            "status_code": 0,
            "marker_present_in_model_output": False,
            "marker_appended_by_wrapper": False,
            "error": None,
        }, output_text="""## Metadata
- model: fake

## Files Read
- docs/autoresearch_workflow.md

## Commands Run
- python3 scripts/autoresearch_fake_worker.py

## Artifacts Produced
- worker_output.md

## Verification Summary
All checks passed, no API calls made.

## Result
AUTORESEARCH_FAKE_WORKER_RESULT:PASS
""")
        result = review_issue(wf_dir)
        assert result.verdict == "PASS"
        assert result.score == 100

    def test_fake_worker_without_marker_fails(self, coordinator):
        """Fake worker output without marker should FAIL."""
        wf_dir = _make_workflow_with_metadata(coordinator, "test-fake-nomark", {
            "model": "fake",
            "input_tokens": 0,
            "output_tokens": 0,
            "status_code": 0,
            "marker_present_in_model_output": False,
            "marker_appended_by_wrapper": False,
            "error": None,
        }, output_text="Just some text without any marker.")
        result = review_issue(wf_dir)
        # No AUTORESEARCH_FAKE_WORKER_RESULT:PASS → falls through to real path
        # No worker_metadata.json with proper data → at minimum scored down
        # Actually there IS a worker_metadata.json but with status_code=0
        # → falls through to real path with bad metadata → should score < 100
        assert result.score < 100

    def test_fake_worker_no_metadata_required(self, coordinator):
        """Fake worker auto-detect should not require worker_metadata.json."""
        # Create a workflow WITHOUT metadata, only fake worker output.
        state = coordinator.create_workflow("test-fake-nometa", "# Test\n")
        adir = coordinator.attempt_dir("test-fake-nometa", 1)
        adir.mkdir(parents=True, exist_ok=True)
        out = adir / "worker_output.md"
        out.write_text("""## Metadata
- model: fake

## Files Read
- none

## Commands Run
- fake

## Artifacts Produced
- out.md

## Verification Summary
OK

## Result
AUTORESEARCH_FAKE_WORKER_RESULT:PASS
""")
        wf_dir = coordinator.workflow_dir("test-fake-nometa")
        result = review_issue(wf_dir)
        assert result.verdict == "PASS"
        assert result.score == 100


# ── Codex review writer ───────────────────────────────────────────────────────

class TestWriteCodexReview:
    def test_output_format(self, tmp_path):
        result = ReviewResult(
            issue_id="test-issue",
            verdict="PASS",
            score=100,
            checks=[{"check": "http_status_200", "result": "PASS"}],
            evidence=["state.json loaded"],
            warnings=[],
            next_action="proceed",
        )
        out = tmp_path / "codex_review.md"
        write_codex_review(result, out)
        assert out.is_file()
        content = out.read_text()
        assert "VERDICT: PASS" in content
        assert "SCORE: 100/100" in content
        assert "AUTORESEARCH_RESULT:PASS" in content
        assert "## Checks" in content
        assert "## Evidence" in content
        assert "## Next Action" in content

    def test_warn_output_includes_warnings(self, tmp_path):
        result = ReviewResult(
            issue_id="test-warn",
            verdict="WARN",
            score=75,
            checks=[],
            evidence=[],
            warnings=["claims zero cost but tokens consumed"],
            next_action="owner review",
        )
        out = tmp_path / "codex_review.md"
        write_codex_review(result, out)
        content = out.read_text()
        assert "## Warnings" in content
        assert "claims zero cost" in content
        assert "WARNING" in content
