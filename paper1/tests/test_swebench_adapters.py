from __future__ import annotations

from types import SimpleNamespace

import pytest

from budgetflow.adapters import (
    SwebenchBudgetAdapter,
    SwebenchCostAdapter,
    SwebenchProgressAdapter,
    SwebenchTaskAdapter,
)
from budgetflow.types import Stage, WorkflowSegment


def test_swebench_task_adapter_normalizes_task_features() -> None:
    task = SimpleNamespace(
        instance_id="repo__task-1",
        patch="diff --git a/x b/x\n+one\n+two\n",
        fail_to_pass=("test_a", "test_b"),
        pass_to_pass=("test_c",),
        problem_statement="Fix the behavior.",
    )

    adapter = SwebenchTaskAdapter()

    assert adapter.instance_id(task) == "repo__task-1"
    assert adapter.features(task).as_record() == {
        "patch_lines": 3,
        "f2p_count": 2,
        "p2p_count": 1,
        "problem_length": 17,
    }


def test_swebench_progress_adapter_normalizes_result_fields() -> None:
    result = SimpleNamespace(
        harness_resolved=True,
        harness_detail="test_patch=ok",
        patch_text="diff",
        patch_source="workspace_diff",
        submitted_patch_path="/tmp/submitted.patch",
        workspace_patch_path="/tmp/workspace.patch",
    )

    outcome = SwebenchProgressAdapter().outcome_from_result(result)

    assert outcome.as_record() == {
        "harness_resolved": True,
        "patch_extracted": True,
        "patch_source": "workspace_diff",
        "submitted_patch": "/tmp/submitted.patch",
        "workspace_patch": "/tmp/workspace.patch",
        "detail": "test_patch=ok",
    }


def test_swebench_cost_adapter_fails_fast_for_unknown_backend() -> None:
    with pytest.raises(ValueError, match="unknown backend"):
        SwebenchCostAdapter().estimate("missing-tier", 100, 20)


def test_swebench_budget_adapter_normalizes_budget_input() -> None:
    budget_input = SwebenchBudgetAdapter().normalize(
        hard_cap_usd=123.0,
        soft_cap_usd=100.0,
        window="policy_batch",
        shared=True,
        budget_scale=1.2,
    )

    assert budget_input["hard_cap_usd"] == 123.0
    assert budget_input["soft_cap_usd"] == 100.0
    assert budget_input["window"] == "policy_batch"
    assert budget_input["source"] == "pre_registered_experiment_budget"
    assert budget_input["shared"] is True
    assert budget_input["confidence"]["budget_scale"] == 1.2
    assert budget_input["allowed_backends"]


def test_swebench_progress_adapter_maps_command_to_segment() -> None:
    signal = SwebenchProgressAdapter().signal_from_context(
        bash_command="pytest tests/test_example.py",
        observation="",
        agent_phase="test",
    )

    assert signal.stage is Stage.VALIDATION
    assert signal.segment.name == WorkflowSegment.VERIFICATION
    assert signal.has_progress is True
    assert signal.progress_reason == "validation_pattern"
    assert signal.touched_file_paths == ["tests/test_example.py"]


def test_swebench_progress_adapter_handles_empty_context() -> None:
    signal = SwebenchProgressAdapter().signal_from_context(
        bash_command=None,
        observation="",
        agent_phase=None,
    )

    assert signal.stage is Stage.LOCALIZATION
    assert signal.segment.name == WorkflowSegment.CONTEXT
    assert signal.has_progress is False
    assert signal.touched_file_paths == []


def test_swebench_progress_adapter_maps_edit_phase_to_action_segment() -> None:
    signal = SwebenchProgressAdapter().signal_from_context(
        bash_command="grep -R pattern src",
        observation="",
        agent_phase="edit_gold",
    )

    assert signal.stage is Stage.REPAIR
    assert signal.segment.name == WorkflowSegment.ACTION
