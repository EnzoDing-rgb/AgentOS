from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from budgetflow.adapter.runner import run_mini_swe_task
from budgetflow.governor import BudgetGovernor, GovernorConfig
from budgetflow.ledger import WorkflowLedgerStore


class _FakeTrace:
    ignore_changed_files: tuple[str, ...] = ()

    def __init__(self, *args, **kwargs) -> None:
        self._summary = {"gold_edited": True, "gold_files": ["sympy/sets/sets.py"]}

    def publish_live_progress(self, *args, **kwargs) -> None:
        return None

    def heartbeat_status(self, *args, **kwargs) -> str:
        return ""

    def agent_summary(self) -> dict:
        return dict(self._summary)

    def finalize_agent(self, *args, **kwargs) -> None:
        return None

    def log_harness_result(self, *args, **kwargs) -> None:
        return None


class _FakeAgent:
    def __init__(self, *args, **kwargs) -> None:
        self.n_calls = 1

    def run(self, task: str) -> dict:
        raise NameError("nonfatal agent wrapper error after edit")


def _patch_runner_boundaries(monkeypatch, tmp_path: Path, *, harness_resolved: bool, harness_detail: str) -> None:
    import budgetflow.adapter.runner as runner

    monkeypatch.setattr(runner, "clone_or_checkout", lambda *args, **kwargs: tmp_path)
    monkeypatch.setattr(runner, "get_last_compat_files", lambda: ())
    monkeypatch.setattr(runner, "get_trace_dir", lambda *args, **kwargs: tmp_path)
    monkeypatch.setattr(runner, "RunTraceLogger", _FakeTrace)
    monkeypatch.setattr(runner, "patch_local_swebench_config", lambda config, repo_dir: config)
    monkeypatch.setattr(runner, "_load_agent_config", lambda step_limit: {"agent": {}, "environment": {}, "model": {}})
    monkeypatch.setattr(runner, "build_backends_for_strategy", lambda strategy: [])
    monkeypatch.setattr(runner, "build_routing_context", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(runner, "BudgetFlowLitellmModel", lambda *args, **kwargs: SimpleNamespace(
        _progress_refresh=None,
        last_exit_reason=None,
        last_budget_snapshot=None,
        backend_picks=("tier3",),
        step_index=1,
        _total_prompt_tokens=10,
        _total_completion_tokens=5,
        turn_traces=[],
        _protocol_retry_used=False,
        _protocol_retry_success=False,
        _protocol_retry_reason="",
        _protocol_retry_attempts=0,
        _protocol_retry_limit=4,
    ))
    monkeypatch.setattr(runner, "LocalEnvironment", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(runner, "TracedDefaultAgent", _FakeAgent)
    monkeypatch.setattr(runner, "extract_worktree_patch", lambda *args, **kwargs: "diff --git a/sympy/sets/sets.py b/sympy/sets/sets.py\n")
    monkeypatch.setattr(
        runner,
        "evaluate_local_harness",
        lambda *args, **kwargs: SimpleNamespace(harness_resolved=harness_resolved, detail=harness_detail),
    )


def _run_fake_task() -> object:
    task = SimpleNamespace(
        instance_id="sympy__sympy-16988",
        problem_statement="fix it",
        gold_files=("sympy/sets/sets.py",),
    )
    ledger = WorkflowLedgerStore()
    governor = BudgetGovernor(GovernorConfig(total_budget=1.0, default_max_output_tokens=4096), ledger)

    return run_mini_swe_task(
        task,
        governor=governor,
        ledger=ledger,
        strategy="bare_t3",
        strategy_label="bare_t3_baseline",
        agent_heartbeat=False,
    )


def test_runner_normalizes_resolved_worktree_patch_exit_status(monkeypatch, tmp_path: Path) -> None:
    _patch_runner_boundaries(
        monkeypatch,
        tmp_path,
        harness_resolved=True,
        harness_detail="test_patch=ok; fail_before=fail; model_patch=ok; fail_after=pass; pass_to_pass=pass",
    )

    result = _run_fake_task()

    assert result.harness_resolved is True
    assert result.exit_status == "HarnessResolved"
    assert result.exit_reason == "harness_resolved"
    assert result.agent_exit_status == "NameError"
    assert result.agent_exit_reason == "NameError"
    assert result.patch_source == "worktree"


def test_runner_normalizes_evaluated_failed_patch_exit_status(monkeypatch, tmp_path: Path) -> None:
    _patch_runner_boundaries(
        monkeypatch,
        tmp_path,
        harness_resolved=False,
        harness_detail="test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail; pass_to_pass=pass",
    )

    result = _run_fake_task()

    assert result.harness_resolved is False
    assert result.exit_status == "HarnessFailed"
    assert result.exit_reason == "harness_failed"
    assert result.agent_exit_status == "NameError"
    assert result.agent_exit_reason == "NameError"
