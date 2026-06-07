"""Tests for 019 features: harness_trust, verdict, BudgetMemory, strategy aliases,
offline replay, completed heartbeat not stale."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import pytest
from budgetflow.check_run_observability import (
    _pid_is_alive,
    _rows_stuck,
    check_jsonl,
)
from budgetflow.observability import (
    HeartbeatWriter,
    build_harness_trust,
    parse_harness_evidence,
)
from budgetflow.failure_classification import build_verdict, classify_failure
from budgetflow.budget_memory import BudgetMemory, BudgetEstimate
from budgetflow.offline_replay import run_replay


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_record(**kw):
    """Minimal valid record dict."""
    defaults = {
        "instance_id": "sympy__sympy-99999",
        "strategy": "budget_only_tight",
        "routing": "budget_only",
        "harness_resolved": False,
        "exit_status": "BudgetFlowBudgetError",
        "exit_reason": "budget_exhausted",
        "total_cost": 0.5,
        "llm_turns": 10,
        "elapsed_s": 30.0,
        "detail": "test_patch=ok;fail_before=fail;model_patch=ok;fail_after=fail;pass_to_pass=ok",
        "turn_trace_count": 5,
        "run_series": "test",
        "policy_lane": "test",
        "task_order_index": 0,
        "row_started_at": 1000.0,
        "row_finished_at": 1030.0,
        "observability_status": {},
        "harness_evidence": {"evidence_complete": True},
    }
    defaults.update(kw)
    if "harness_evidence" not in kw and "detail" in kw:
        ev = parse_harness_evidence(defaults["detail"])
        defaults["harness_evidence"] = ev.__dict__
    return defaults


# ── Completed heartbeat not stale ─────────────────────────────────────────────

class TestCompletedHeartbeatNotStale:
    def test_completed_heartbeat_no_stale(self, tmp_path):
        hb_path = tmp_path / "test_run.heartbeat.json"
        hb_path.write_text(json.dumps({
            "started_at": 1000.0,
            "updated_at": 1001.0,
            "total_expected": 50,
            "rows_done": 50,
            "active_strategy": "all_pro",
            "active_instance": "sympy__sympy-20212",
            "current_pid": 0,
            "status": "completed",
            "run_series": "test_run",
        }))

        jsonl_path = tmp_path / "test.jsonl"
        rec = _make_record(run_series="test_run")
        jsonl_path.write_text(json.dumps(rec) + "\n")

        result = check_jsonl(jsonl_path, heartbeat_stale_s=0.1)
        assert not result.get("heartbeat_stale")
        assert not result.get("heartbeat_suspicious")

    def test_dead_pid_still_suspicious(self, tmp_path):
        hb_path = tmp_path / "test_run.heartbeat.json"
        hb_path.write_text(json.dumps({
            "started_at": 1000.0,
            "updated_at": 1001.0,
            "total_expected": 50,
            "rows_done": 30,
            "current_pid": 999999,
            "status": "running",
            "run_series": "test_run",
        }))

        jsonl_path = tmp_path / "test.jsonl"
        rec = _make_record(run_series="test_run")
        jsonl_path.write_text(json.dumps(rec) + "\n")

        result = check_jsonl(jsonl_path, heartbeat_stale_s=0.1)
        assert result.get("heartbeat_suspicious")

    def test_rows_stuck_completed_ok(self):
        hb = {"rows_done": 10, "total_expected": 10, "status": "completed",
              "updated_at": 1001.0, "started_at": 1000.0}
        stuck, _ = _rows_stuck(hb, 0.1)
        assert not stuck

    def test_rows_stuck_completed_incomplete(self):
        hb = {"rows_done": 5, "total_expected": 10, "status": "completed",
              "updated_at": 1001.0, "started_at": 1000.0}
        stuck, reason = _rows_stuck(hb, 0.1)
        assert stuck
        assert "crashed" in reason


# ── Harness trust (updated: trusted_fallback + severity) ──────────────────────

class TestHarnessTrust:
    def test_trusted_pass(self):
        rec = _make_record(
            harness_resolved=True,
            patch_extracted=True,
            patch_source="submission",
            submitted_patch="/tmp/patch.diff",
            agent_submitted=True,
            agent_attempted_submit=True,
            agent_gold_edited=True,
            agent_gold_files=["file.py"],
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=pass;pass_to_pass=pass",
        )
        ht = build_harness_trust(rec)
        assert ht["harness_trust"] == "trusted"
        assert ht["harness_owner"] == "none"
        assert ht["severity"] == "none"
        assert ht["harness_issues"] == []

    def test_trusted_fallback_worktree_with_evidence(self):
        """Worktree fallback + evidence complete → trusted_fallback, severity=warn."""
        rec = _make_record(
            harness_resolved=True,
            patch_extracted=True,
            patch_source="worktree",
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=pass;pass_to_pass=pass",
        )
        ht = build_harness_trust(rec)
        assert ht["harness_trust"] == "trusted_fallback"
        assert ht["severity"] == "warn"
        assert "patch_from_worktree_fallback" in ht["harness_issues"]

    def test_incomplete_no_patch(self):
        rec = _make_record(
            harness_resolved=False,
            patch_extracted=False,
            patch_source="none",
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=fail;pass_to_pass=ok",
        )
        ht = build_harness_trust(rec)
        assert ht["harness_trust"] == "incomplete"
        assert "no_patch_extracted" in ht["harness_issues"]

    def test_invalid_pass_missing_fail_after(self):
        """PASS but fail_after missing → invalid, severity=blocking."""
        rec = _make_record(
            harness_resolved=True,
            patch_extracted=True,
            patch_source="submission",
            submitted_patch="/tmp/patch.diff",
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=fail;pass_to_pass=ok",
        )
        ht = build_harness_trust(rec)
        assert ht["harness_trust"] == "invalid"
        assert ht["severity"] == "blocking"

    def test_blocking_pass_to_pass_missing(self):
        """PASS but pass_to_pass missing → invalid, severity=blocking."""
        rec = _make_record(
            harness_resolved=True,
            patch_extracted=True,
            patch_source="submission",
            submitted_patch="/tmp/patch.diff",
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=pass;pass_to_pass=fail",
        )
        ht = build_harness_trust(rec)
        assert ht["harness_trust"] == "invalid"
        assert ht["severity"] == "blocking"

    def test_suspicious_nonblocking_gap(self):
        """PASS with fail_before missing only → suspicious (non-blocking)."""
        rec = _make_record(
            harness_resolved=True,
            patch_extracted=True,
            patch_source="submission",
            submitted_patch="/tmp/patch.diff",
            detail="test_patch=ok;fail_before=ok;model_patch=ok;fail_after=pass;pass_to_pass=pass",
        )
        ht = build_harness_trust(rec)
        assert ht["harness_trust"] == "suspicious"
        assert "fail_before_not_failed" in ht["harness_issues"]

    def test_harness_owner_from_gaps(self):
        rec = _make_record(
            harness_resolved=False,
            detail="test_patch=fail;fail_before=fail;model_patch=ok;fail_after=fail;pass_to_pass=ok",
        )
        ht = build_harness_trust(rec)
        assert ht["harness_owner"] == "harness"

    def test_protocol_owner(self):
        rec = _make_record(
            harness_resolved=False,
            patch_extracted=False,
            patch_source="none",
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=fail;pass_to_pass=ok",
        )
        ht = build_harness_trust(rec)
        assert ht["harness_owner"] == "protocol"


# ── Verdict observability ────────────────────────────────────────────────────

class TestVerdictObservability:
    def test_pass_verdict(self):
        rec = _make_record(
            harness_resolved=True,
            patch_extracted=True,
            patch_source="submission",
            agent_gold_edited=True,
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=pass;pass_to_pass=pass",
            exit_status="submitted",
            exit_reason="submitted",
        )
        v = build_verdict(rec)
        assert v["verdict_axis"] == "pass"
        assert v["failure_owner"] == "none"
        assert v["failure_stage"] == "none"

    def test_budget_fail_verdict(self):
        rec = _make_record(harness_resolved=False)
        v = build_verdict(rec)
        assert v["verdict_axis"] == "budget_fail"
        assert v["failure_owner"] == "budget"

    def test_model_fail_verdict(self):
        rec = _make_record(
            harness_resolved=False,
            patch_extracted=True,
            agent_gold_edited=True,
            exit_status="StagnationExit",
            exit_reason="stagnation_no_progress",
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=fail;pass_to_pass=ok",
        )
        v = build_verdict(rec)
        assert v["verdict_axis"] == "model_fail"
        assert v["failure_owner"] == "model"

    def test_protocol_fail_verdict(self):
        rec = _make_record(
            harness_resolved=False,
            patch_extracted=False,
            exit_status="BadRequestError",
            exit_reason="format_error",
            detail="",
            turn_trace_count=0,
        )
        v = build_verdict(rec)
        assert v["verdict_axis"] == "protocol_fail"
        assert v["failure_owner"] == "protocol"

    def test_evidence_complete_detection(self):
        rec = _make_record(
            harness_resolved=True,
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=pass;pass_to_pass=pass",
            turn_trace_count=5,
        )
        v = build_verdict(rec)
        assert v["evidence_complete"] is True

    def test_missing_evidence(self):
        rec = _make_record(harness_resolved=False, detail="", turn_trace_count=0)
        v = build_verdict(rec)
        assert v["evidence_complete"] is False
        assert "harness_detail" in v["missing_evidence"]


# ── BudgetMemory ─────────────────────────────────────────────────────────────

class TestBudgetMemory:
    def _sample_records(self) -> list[dict]:
        records = []
        for i in range(5):
            records.append(_make_record(
                instance_id="sympy__sympy-12345",
                strategy="budget_only_tight",
                total_cost=0.5 + i * 0.05,
                harness_resolved=(i < 3),
                exit_status="submitted" if i < 3 else "BudgetFlowBudgetError",
                exit_reason="submitted" if i < 3 else "budget_exhausted",
            ))
        for i in range(3):
            records.append(_make_record(
                instance_id="sympy__sympy-67890",
                strategy="budgetflow_full_tight",
                total_cost=1.0 + i * 0.1,
                harness_resolved=(i < 2),
            ))
        return records

    def test_from_jsonl_path(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        records = self._sample_records()
        jsonl.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        bm = BudgetMemory.from_jsonl(str(jsonl))
        assert bm.record_count == 8
        assert bm.task_count >= 2

    def test_exact_task_estimate(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        records = self._sample_records()
        jsonl.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        bm = BudgetMemory.from_jsonl(str(jsonl))
        est = bm.estimate_task_budget("sympy__sympy-12345", strategy="budget_only_tight")
        assert est.budget_source == "exact_task"
        assert est.budget_confidence in ("high", "medium")
        assert est.estimated_task_budget > 0
        assert not est.hard_budget_used

    def test_repo_median_fallback(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        records = self._sample_records()
        jsonl.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        bm = BudgetMemory.from_jsonl(str(jsonl))
        est = bm.estimate_task_budget("sympy__sympy-99999", repo="sympy")
        assert est.budget_source in ("repo_median", "strategy_median", "global_fallback")

    def test_hard_budget_respected(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        records = self._sample_records()
        jsonl.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        bm = BudgetMemory.from_jsonl(str(jsonl))
        est = bm.estimate_task_budget("sympy__sympy-12345", hard_budget=0.10)
        assert est.hard_budget_used
        assert est.estimated_task_budget <= 0.10

    def test_empty_memory_global_fallback(self):
        bm = BudgetMemory()
        est = bm.estimate_task_budget("unknown__task", strategy="all_pro")
        assert est.budget_source == "global_fallback"
        assert est.budget_confidence == "low"
        assert est.estimated_task_budget > 0

    def test_demo_output(self, tmp_path):
        """BudgetMemory.run_demo produces offline estimate output without API calls."""
        from budgetflow.budget_memory import run_demo
        jsonl = tmp_path / "test.jsonl"
        records = self._sample_records()
        jsonl.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        output = run_demo([str(jsonl)])
        assert "BudgetMemory offline demo" in output
        assert "NOT yet integrated" in output
        assert "sympy__sympy-12345" in output


# ── Strategy aliases ─────────────────────────────────────────────────────────

class TestStrategyAliases:
    def test_strategy_names_are_canonical_only(self):
        from budgetflow.experiments.compare_config import normalize_strategy
        assert normalize_strategy("old_budget_alias") == "old_budget_alias"
        assert normalize_strategy("old_budgetflow_alias") == "old_budgetflow_alias"

    def test_dummy_is_real_strategy(self):
        """budget_tight_dummy is a real CompareStrategy, not just alias."""
        from budgetflow.experiments.compare_config import normalize_strategy, strategy_catalog
        names = {s.name for s in strategy_catalog()}
        assert "budget_tight_dummy" in names
        assert normalize_strategy("budget_tight_dummy") == "budget_tight_dummy"

    def test_old_names_are_not_rewritten(self):
        from budgetflow.experiments.compare_config import normalize_strategy
        assert normalize_strategy("budget_only_tight") == "budget_only_tight"
        assert normalize_strategy("old_tier1_alias") == "old_tier1_alias"


# ── Offline replay ───────────────────────────────────────────────────────────

class TestOfflineReplay:
    def test_replay_basic(self, tmp_path):
        p017 = tmp_path / "017.jsonl"
        p018 = tmp_path / "018.jsonl"

        for i in range(10):
            rec = _make_record(
                instance_id=f"sympy__sympy-{10000+i}",
                strategy="budget_only_tight",
                run_series="postfix_017",
                total_cost=0.5 + i * 0.02,
            )
            p017.write_text((p017.read_text() if p017.exists() else "") + json.dumps(rec) + "\n")
            rec2 = _make_record(
                instance_id=f"sympy__sympy-{10000+i}",
                strategy="budget_only_tight",
                run_series="postfix_018",
                total_cost=0.45 + i * 0.02,
                policy_memory_enabled=True,
                routing_prior_summary={"learned_action": "default", "policy_memory_source": "017.jsonl"},
            )
            p018.write_text((p018.read_text() if p018.exists() else "") + json.dumps(rec2) + "\n")

        output = run_replay(p017, p018)
        assert "SUMMARY: 017 vs 018" in output
        assert "PER-TASK" in output
        assert "FAILURE OWNERSHIP" in output
        assert "HARNESS TRUST" in output
        assert "POLICY MEMORY EFFECT" in output

    def test_replay_old_jsonl_has_owner(self, tmp_path):
        """Old JSONL without verdict_axis/failure_owner must still produce
        non-empty failure owner via dynamic build_verdict()."""
        p017 = tmp_path / "017.jsonl"
        p018 = tmp_path / "018.jsonl"

        # Simulate old JSONL: no verdict_axis, no failure_owner
        for i in range(5):
            rec = _make_record(
                instance_id=f"sympy__sympy-{20000+i}",
                strategy="budgetflow_full_tight",
                harness_resolved=(i < 2),  # 2 pass, 3 fail
                exit_status="BudgetFlowBudgetError" if i >= 2 else "submitted",
                exit_reason="budget_exhausted" if i >= 2 else "submitted",
                total_cost=1.0 + i * 0.1,
            )
            # Ensure no pre-existing verdict fields
            rec.pop("verdict_axis", None)
            rec.pop("failure_owner", None)
            p018.write_text((p018.read_text() if p018.exists() else "") + json.dumps(rec) + "\n")

        # Also populate p017 minimally
        p017.write_text(json.dumps(_make_record(instance_id="sympy__sympy-20000", strategy="budgetflow_full_tight")) + "\n")

        output = run_replay(p017, p018)
        assert "FAILURE OWNERSHIP" in output
        # Must NOT be empty — build_verdict is called dynamically
        assert "By owner:" in output
        # budget should appear as owner for budget_exhausted failures
        assert "budget" in output

    def test_replay_empty_file(self, tmp_path):
        p017 = tmp_path / "017.jsonl"
        p018 = tmp_path / "018.jsonl"
        p017.write_text("")
        p018.write_text(json.dumps(_make_record()) + "\n")
        output = run_replay(p017, p018)
        assert "ERROR" in output


# ── Compact audit integration ────────────────────────────────────────────────

class TestCompactAudit019Fields:
    def test_harness_trust_in_audit(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        rec = _make_record(
            harness_resolved=True,
            patch_extracted=True,
            patch_source="submission",
            submitted_patch="/tmp/p.diff",
            agent_submitted=True,
            agent_attempted_submit=True,
            agent_gold_edited=True,
            agent_gold_files=["f.py"],
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=pass;pass_to_pass=pass",
        )
        jsonl.write_text(json.dumps(rec) + "\n")

        from budgetflow.check_run_observability import build_compact_audit, format_compact_audit
        records = [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]
        audit = build_compact_audit(records)
        assert "harness_trust" in audit
        assert "trusted" in audit["harness_trust"]
        assert "harness_severity" in audit
        text = format_compact_audit(audit)
        assert "HARNESS TRUST" in text
        # HARNESS SEVERITY only appears if severity != none
        assert audit.get("harness_severity") is not None

    def test_verdict_fields_in_audit(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        rec = _make_record(
            harness_resolved=False,
            exit_status="BudgetFlowBudgetError",
            exit_reason="budget_exhausted",
        )
        v = build_verdict(rec)
        rec.update({k: v[k] for k in ["verdict_axis", "failure_owner", "failure_stage",
                                        "evidence_complete", "missing_evidence"]})
        jsonl.write_text(json.dumps(rec) + "\n")

        from budgetflow.check_run_observability import build_compact_audit, format_compact_audit
        records = [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]
        audit = build_compact_audit(records)
        assert "verdict_owners" in audit
        assert "budget" in audit["verdict_owners"]
        text = format_compact_audit(audit)
        assert "OWNER SUMMARY" in text
