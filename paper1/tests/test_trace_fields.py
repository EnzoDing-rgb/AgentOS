from __future__ import annotations

import pytest

# mini_swe_proxy imports minisweagent, which may not be installed.
_minisweagent_available = True
try:
    from budgetflow.adapter.mini_swe_proxy import BudgetFlowLitellmModel  # noqa: F401
except ImportError:
    _minisweagent_available = False

from budgetflow.adapter.turn_trace import (
    build_turn_trace,
    cost_basis_trace_fields,
    protocol_trace_fields,
    provider_trace_fields,
)
from budgetflow.adapter.strategies import build_routing_context
from budgetflow.model_tiers import MODEL_CATALOG
from budgetflow.types import Backend, Stage, WorkflowSegment


def _backend(name: str, tier: int) -> Backend:
    return Backend(name, tier, 0.001 * tier, 0.002 * tier, 60, 1, 1024, 0.5, 100)


def test_local_swebench_config_isolates_agent_shell_from_global_python(tmp_path) -> None:
    from budgetflow.run_trace import patch_local_swebench_config

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    config = {"agent": {"instance_template": "work in /testbed"}, "environment": {"env": {"KEEP": "1"}}}

    patched = patch_local_swebench_config(config, repo_dir)

    env = patched["environment"]["env"]
    assert patched["agent"]["instance_template"] == f"work in {repo_dir}"
    assert patched["environment"]["cwd"] == str(repo_dir)
    assert env["KEEP"] == "1"
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["PIP_REQUIRE_VIRTUALENV"] == "1"


def test_agent_environment_issue_scans_beyond_observation_preview() -> None:
    from budgetflow.run_trace import _agent_environment_issue, _last_observation_summary

    long_prefix = "x" * 260
    messages = [
        {
            "role": "user",
            "content": (
                "<returncode>1</returncode>"
                f"<output>{long_prefix} ImportError: cannot import name 'environmentfilter' "
                "from 'jinja2'</output>"
            ),
        }
    ]

    observation = _last_observation_summary(messages)

    assert _agent_environment_issue(observation) == "ImportError: cannot import name"


def test_runner_aborts_before_provider_calls_on_global_runtime_worktree_contamination(monkeypatch) -> None:
    import budgetflow.adapter.runner as runner

    def fail_if_called(*args, **kwargs):
        raise AssertionError("provider run should not start when host Python is contaminated")

    monkeypatch.setattr(
        runner,
        "find_runtime_worktree_python_contamination",
        lambda runtime_root: ["site-packages/stale.pth: /tmp/budgetflow-runtime/worktrees/repo/task"],
    )
    monkeypatch.setattr(runner, "clone_or_checkout", fail_if_called)

    task = type("Task", (), {"instance_id": "repo__task"})()

    result = runner.run_mini_swe_task(task, strategy="bare_t3", strategy_label="bare_t3_baseline")

    assert result.exit_status == "infra_error"
    assert result.exit_reason == "host_dependency_contamination"
    assert result.agent_exit_status == "infra_error"
    assert result.total_cost == 0.0
    assert result.llm_turns == 0
    assert result.backend_picks == ()
    assert result.usage_source == "none"
    assert result.cost_mode == "no_provider_call"
    assert "host_dependency_contamination" in result.harness_detail


def test_turn_trace_has_fields_needed_to_debug_value_routing_and_provider_failures() -> None:
    trace = build_turn_trace(
        step_index=1,
        agent_phase="edit_gold",
        stage=Stage.REPAIR,
        workflow_segment=WorkflowSegment.action(agent_phase="edit_gold", touched_files=1),
        bash_command="git diff",
        touched_file_paths=["src/file.py"],
        input_tokens=100,
        expected_costs={"tier2": 0.01},
        base_pressure=0.1,
        effective_pressure=0.2,
        backend_chosen="tier2",
        escalated_backend="tier3",
        final_backend="tier3",
        backend_tier=3,
        reserve_out=512,
        adaptive=None,
        no_progress_streak=4,
        no_progress_on_tier=3,
        turns_on_tier=2,
        has_progress=True,
        progress_reason="repair_pattern",
        action_has_progress=True,
        action_progress_reason="action_repair_pattern",
        action_digest="python - <<'PY'\nfrom pathlib import Path\nPath('src/file.py').write_text('x')\nPY",
        action_touched_file_paths=["src/file.py"],
        prompt_tokens=100,
        completion_tokens=50,
        prompt_tokens_source="provider",
        completion_tokens_source="provider",
        cost_mode="catalog_provider_usage",
        actual_cost=0.02,
        billable=0.02,
        response_ok=False,
        error_type="ServiceUnavailableError",
        provider="openai_compatible",
        model="openai/gpt-5.4",
        cost_estimate_source="tier_catalog:test",
        cost_estimate_confidence={"backend": "tier3"},
        protocol="tool_call",
        parser="parse_toolcall_actions",
        provider_status_code=503,
        provider_error_kind="transient_provider",
        provider_retryable=True,
        router_reason="value_triggered_escalation",
        router_branch="segment_value_aware",
        routing_trigger_source="value_escalation",
        task_value=2.0,
        task_value_multiplier=1.5,
        value_aware_active=True,
        value_triggered_escalation_active=True,
        value_triggered_escalation_turns_remaining=2,
        value_triggered_escalation_opened=True,
        value_triggered_escalation_reason="opened_stagnation_no_progress",
        value_triggered_escalation_action="default",
        value_triggered_escalation_window=3,
    )

    assert trace["turns_on_tier"] == 2
    assert trace["workflow_segment"] == "Action"
    assert trace["segment_signals"]["agent_phase"] == "edit_gold"
    assert trace["progress_state"] == "progress"
    assert trace["action_progress_state"] == "progress"
    assert "Path('src/file.py')" in trace["action_digest"]
    assert trace["action_touched_file_paths"] == ["src/file.py"]
    assert trace["touched_file_paths"] == ["src/file.py"]
    assert trace["provider"] == "openai_compatible"
    assert trace["usage_source"] == "provider"
    assert trace["cost_mode"] == "catalog_provider_usage"
    assert trace["cost_estimate_source"] == "tier_catalog:test"
    assert trace["cost_estimate_confidence"]["backend"] == "tier3"
    assert trace["protocol"] == "tool_call"
    assert trace["provider_status_code"] == 503
    assert trace["provider_error_kind"] == "transient_provider"
    assert trace["provider_retryable"] is True
    assert trace["router_branch"] == "segment_value_aware"
    assert trace["routing_trigger_source"] == "value_escalation"
    assert trace["task_value_multiplier"] == 1.5
    assert trace["value_triggered_escalation_active"] is True
    assert trace["value_triggered_escalation_turns_remaining"] == 2
    assert trace["value_triggered_escalation_opened"] is True
    assert trace["value_triggered_escalation_action"] == "default"


def test_turn_trace_preserves_unknown_progress_state() -> None:
    trace = build_turn_trace(
        step_index=1,
        agent_phase=None,
        stage=Stage.LOCALIZATION,
        workflow_segment=WorkflowSegment.context(agent_phase=None),
        bash_command=None,
        input_tokens=10,
        expected_costs={},
        base_pressure=0.0,
        effective_pressure=0.0,
        backend_chosen="tier2",
        escalated_backend="tier2",
        final_backend="tier2",
        backend_tier=2,
        reserve_out=0,
        adaptive=None,
        no_progress_streak=0,
        no_progress_on_tier=0,
        turns_on_tier=1,
        has_progress=None,
        progress_reason="unknown",
        action_has_progress=None,
        action_progress_reason="unknown",
        prompt_tokens=10,
        completion_tokens=0,
        actual_cost=0.0,
        billable=0.0,
        response_ok=True,
        error_type=None,
    )

    assert trace["progress_state"] == "unknown"
    assert trace["action_progress_state"] == "unknown"


def test_swebench_progress_adapter_emits_workflow_segment_and_progress_signal() -> None:
    from budgetflow.adapters import SwebenchProgressAdapter

    adapter = SwebenchProgressAdapter()
    signal = adapter.signal_from_context(
        bash_command="apply_patch <<'PATCH'\n*** Begin Patch\n*** End Patch\nPATCH",
        observation="",
        agent_phase="edit_gold",
    )

    assert signal.stage is Stage.REPAIR
    assert signal.segment.name == WorkflowSegment.ACTION
    assert signal.has_progress is True
    assert signal.progress_reason == "repair_pattern"


def test_provider_and_protocol_helpers_identify_real_backend_contracts() -> None:
    provider_fields = provider_trace_fields("tier2")
    tier2 = MODEL_CATALOG.require_config("tier2")
    assert provider_fields["provider"] == "openai_compatible"
    assert provider_fields["model"] == tier2.model
    assert provider_fields["cost_updated"] == tier2.cost_updated
    assert provider_fields["progress_updated"] == tier2.progress_updated
    assert "gpt-5.4" in provider_trace_fields("tier3")["model"]
    assert protocol_trace_fields("tier3")["protocol"] == "tool_call"
    assert protocol_trace_fields("tier2")["protocol"] == "tool_call"


def test_cost_basis_trace_fields_use_cost_adapter_contract() -> None:
    fields = cost_basis_trace_fields("tier2", input_tokens=1000)

    assert fields["cost_estimate_source"].startswith("tier_catalog:")
    assert fields["cost_estimate_confidence"]["backend"] == "tier2"
    assert fields["cost_estimate_usd"] > 0
    assert fields["cost_input_per_1m"] > 0
    assert fields["cost_output_per_1m"] > 0


def test_cost_basis_trace_fields_apply_t2_input_kv_cache_discount_after_first_turn() -> None:
    first = cost_basis_trace_fields("tier2", input_tokens=1000, turn_index=1)
    second = cost_basis_trace_fields("tier2", input_tokens=1000, turn_index=2)

    assert first["turn_cache_input_fraction"] == 1.0
    assert second["turn_cache_input_fraction"] == 0.5
    assert second["turn_cache_policy"]["input_kv_cache_discount"] == 0.5
    assert second["cost_input_per_1m"] == pytest.approx(first["cost_input_per_1m"] * 0.5)
    assert second["cost_output_per_1m"] == first["cost_output_per_1m"]
    assert second["cost_estimate_usd"] < first["cost_estimate_usd"]


def test_action_trace_fields_capture_current_tool_call_action() -> None:
    from budgetflow.adapter.turn_trace import action_trace_fields

    command = """cd /work && python - <<'PY'
from pathlib import Path
Path("sympy/functions/elementary/hyperbolic.py").write_text("fixed")
PY"""

    fields = action_trace_fields([{"command": command}])

    assert fields["action_digest"].startswith("cd /work")
    assert fields["action_touched_file_paths"] == ["sympy/functions/elementary/hyperbolic.py"]


@pytest.mark.skipif(not _minisweagent_available, reason="minisweagent not installed")
def test_parser_error_trace_fields_extracts_format_error_action_count() -> None:
    from minisweagent.exceptions import FormatError
    from budgetflow.adapter.turn_trace import parser_error_trace_fields

    exc = FormatError({
        "role": "user",
        "content": "",
        "extra": {"n_actions": 0, "model_response": "THOUGHT only"},
    })

    fields = parser_error_trace_fields(exc)

    assert fields["parser_error_type"] == "FormatError"
    assert fields["parser_error_message"] == "Expected exactly 1 action, found 0."
    assert fields["parser_error_action_count"] == 0


@pytest.mark.parametrize(
    ("task_value", "strategy", "opens"),
    [
        (2.0, "segment_value_aware", True),
        (0.5, "segment_value_aware", False),
        (2.0, "budgetflow_conservative", False),
    ],
)
@pytest.mark.skipif(not _minisweagent_available, reason="minisweagent not installed")
def test_value_triggered_escalation_only_opens_for_high_value(task_value: float, strategy: str, opens: bool) -> None:
    t2 = _backend("tier2", 2)
    t3 = _backend("tier3", 3)
    model = object.__new__(BudgetFlowLitellmModel)
    model.routing = build_routing_context(
        strategy,
        [t2, t3],
        budget_pressure=0.01,
        task_value=task_value,
        median_task_value=1.0,
    )
    model._value_triggered_escalation_turns_remaining = 0
    model._value_triggered_escalation_opened = False
    model._value_triggered_escalation_reason = None
    model._value_triggered_escalation_action = "default"
    model._value_triggered_escalation_window = 3
    model._no_progress_on_current_tier = 12
    model._turns_on_current_tier = 12
    model.agent_gold_edited = False
    model.step_index = 12

    class Governor:
        class State:
            total_budget = 1.0

        state = State()

        def remaining_budget(self):
            return 0.8

    model.governor = Governor()

    assert model._maybe_open_value_triggered_escalation("stagnation_no_progress") is opens


def test_router_trace_fields_emit_minimal_policy_decision_record() -> None:
    from budgetflow.adapter.strategies import choose_backend
    from budgetflow.adapter.turn_trace import router_trace_fields
    from budgetflow.types import TurnInfo

    t1 = _backend("tier1", 1)
    t2 = _backend("tier2", 2)
    routing = build_routing_context("budgetflow_conservative", [t1, t2])
    turn = TurnInfo(workflow_id="t", step_index=1, stage=Stage.REPAIR, w_i=0.5, context_len=100)

    backend = choose_backend(routing, turn, {"tier1": 0.01, "tier2": 0.02})
    fields = router_trace_fields(routing)

    assert backend.name in {"tier1", "tier2"}
    assert fields["policy_type"] == "bootstrap"
    assert fields["policy_name"] == "budgetflow_conservative"
    assert fields["memory_mode"] == "off"
    assert fields["policy_decision"]["backend"] in {"tier1", "tier2"}
    assert fields["policy_decision"]["reason"].startswith("bootstrap:")
    assert fields["policy_decision"]["memory_mode"] == "off"


def test_router_trace_fields_report_built_in_memory_mode() -> None:
    from budgetflow.adapter.strategies import build_routing_context, choose_backend
    from budgetflow.adapter.turn_trace import router_trace_fields
    from budgetflow.types import TurnInfo

    t1 = _backend("tier1", 1)
    t2 = _backend("tier2", 2)

    from budgetflow.adaptive_routing import AdaptiveRoutingState

    adaptive = AdaptiveRoutingState("budgetflow_conservative", memory_mode="built_in")
    routing = build_routing_context("budgetflow_conservative", [t1, t2], adaptive=adaptive)
    turn = TurnInfo(workflow_id="t", step_index=1, stage=Stage.REPAIR, w_i=0.5, context_len=100)

    choose_backend(routing, turn, {"tier1": 0.01, "tier2": 0.02})
    fields = router_trace_fields(routing)

    assert fields["policy_type"] == "bootstrap"
    assert fields["memory_mode"] == "built_in"
    assert fields["policy_decision"]["memory_mode"] == "built_in"


def test_router_trace_fields_mark_task_level_as_bootstrap_policy() -> None:
    from budgetflow.adapter.strategies import choose_backend
    from budgetflow.adapter.turn_trace import router_trace_fields
    from budgetflow.types import TurnInfo

    t1 = _backend("tier1", 1)
    t2 = _backend("tier2", 2)
    routing = build_routing_context(
        "value_aware_task_level",
        [t1, t2],
        task_value=2.0,
        median_task_value=1.0,
    )
    turn = TurnInfo(workflow_id="t", step_index=1, stage=Stage.REPAIR, w_i=0.5, context_len=100)

    choose_backend(routing, turn, {"tier1": 0.01, "tier2": 0.02})
    fields = router_trace_fields(routing)

    assert fields["policy_type"] == "bootstrap"
    assert fields["policy_name"] == "value_aware_task_level"
    assert fields["policy_decision"]["router_branch"] == "value_aware_task_level"


@pytest.mark.skipif(not _minisweagent_available, reason="minisweagent not installed")
def test_value_triggered_escalation_honors_memory_disable_window() -> None:
    t2 = _backend("tier2", 2)
    t3 = _backend("tier3", 3)

    class Adaptive:
        _prior_summary = {
            "value_triggered_escalation_action": "disable_value_triggered_escalation",
            "value_triggered_escalation_window": 0,
        }

    model = object.__new__(BudgetFlowLitellmModel)
    model.routing = build_routing_context(
        "segment_value_aware",
        [t2, t3],
        budget_pressure=0.01,
        adaptive=Adaptive(),
        task_value=2.0,
        median_task_value=1.0,
    )
    model._value_triggered_escalation_turns_remaining = 0
    model._value_triggered_escalation_opened = False
    model._value_triggered_escalation_reason = None
    model._value_triggered_escalation_action = "default"
    model._value_triggered_escalation_window = 3
    model.agent_gold_edited = False
    model.step_index = 12

    class Governor:
        class State:
            total_budget = 1.0

        state = State()

        def remaining_budget(self):
            return 0.8

    model.governor = Governor()

    assert model._maybe_open_value_triggered_escalation("stagnation_no_progress") is False
    assert model._value_triggered_escalation_action == "disable_value_triggered_escalation"
    assert model._value_triggered_escalation_window == 0
