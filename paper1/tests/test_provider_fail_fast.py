from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "external" / "mini-swe-agent" / "src"))

from budgetflow.adapter.backends import build_ceiling_backends  # noqa: E402
from budgetflow.adapter.errors import BudgetFlowBudgetError, BudgetFlowUpstreamError  # noqa: E402
from budgetflow.adapter.mini_swe_proxy import BudgetFlowLitellmModel  # noqa: E402
from budgetflow.adapter.strategies import build_routing_context  # noqa: E402
from budgetflow.defaults import TIER3_BACKEND  # noqa: E402
from budgetflow.governor import BudgetGovernor  # noqa: E402
from budgetflow.ledger import WorkflowLedgerStore  # noqa: E402
from budgetflow.run_guards import CompareRunGuards, record_billing_halt, set_active_guard  # noqa: E402
from budgetflow.types import GovernorConfig  # noqa: E402


class ProviderUnavailable(Exception):
    status_code = 503


class _Message:
    content = "THOUGHT: ok\n```bash\nls\n```"
    tool_calls = [
        SimpleNamespace(
            id="call_1",
            function=SimpleNamespace(name="bash", arguments='{"command":"ls"}'),
        )
    ]

    def model_dump(self):
        return {"content": self.content, "tool_calls": self.tool_calls}


class _Response:
    choices = [SimpleNamespace(message=_Message())]
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)

    def model_dump(self):
        return {"choices": [{"message": {"content": _Message.content}}]}


def _model(strategy: str = "all_t3") -> tuple[BudgetFlowLitellmModel, BudgetGovernor]:
    governor = BudgetGovernor(
        GovernorConfig(total_budget=100.0, default_max_output_tokens=128),
        WorkflowLedgerStore(),
    )
    model = BudgetFlowLitellmModel(
        workflow_id="wf-provider",
        governor=governor,
        routing=build_routing_context(strategy, build_ceiling_backends(), budget_pressure=0.1),
        default_max_output_tokens=128,
        enable_turn_trace=True,
    )
    model._api_keys = {
        "DASHSCOPE_API_KEY": "test",
        "DEEPSEEK_API_KEY": "test",
        "AICODE007_API_KEY": "test",
    }
    model._model_config_for = lambda backend: (backend.name, {})
    return model, governor


def test_provider_unavailable_releases_reservation_and_fails_fast(monkeypatch) -> None:
    monkeypatch.setattr("budgetflow.adapter.mini_swe_proxy.load_env_file", lambda: None)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setenv("AICODE007_API_KEY", "test")
    model, governor = _model("all_t3")
    attempts: list[str] = []

    def fake_completion(messages, *, backend_name, **kwargs):
        attempts.append(backend_name)
        raise ProviderUnavailable("ServiceUnavailableError: 503")

    model._completion = fake_completion

    with pytest.raises(BudgetFlowUpstreamError) as excinfo:
        model.query([{"role": "user", "content": "please inspect"}])

    assert attempts == [TIER3_BACKEND]
    assert model.last_exit_reason == "provider_unavailable"
    assert excinfo.value.exit_reason == "provider_unavailable"
    assert excinfo.value.backend == TIER3_BACKEND
    assert governor.state.reserved_budget == pytest.approx(0.0)
    assert governor.state.spent_budget == pytest.approx(0.0)
    assert governor.state.available_budget == pytest.approx(governor.state.total_budget)
    assert len(model.turn_traces) == 1
    assert model.turn_traces[0]["response_ok"] is False
    assert model.turn_traces[0]["final_backend"] == TIER3_BACKEND
    assert model.turn_traces[0]["provider_error_kind"] == "transient_provider"
    assert model.backend_picks == [TIER3_BACKEND]


def test_global_billing_halt_stops_next_turn_before_provider_call(monkeypatch) -> None:
    monkeypatch.setattr("budgetflow.adapter.mini_swe_proxy.load_env_file", lambda: None)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setenv("AICODE007_API_KEY", "test")
    model, governor = _model("all_t3")
    attempts: list[str] = []

    def fake_completion(messages, *, backend_name, **kwargs):
        attempts.append(backend_name)
        return _Response()

    model._completion = fake_completion
    set_active_guard(CompareRunGuards())
    try:
        record_billing_halt("OpenAIException - Insufficient Balance", backend="tier2")
        with pytest.raises(BudgetFlowUpstreamError) as excinfo:
            model.query([{"role": "user", "content": "please inspect"}])
    finally:
        set_active_guard(None)

    assert "billing_guard" in excinfo.value.exit_reason
    assert attempts == []
    assert model.backend_picks == []
    assert governor.state.reserved_budget == pytest.approx(0.0)
    assert governor.state.spent_budget == pytest.approx(0.0)


def test_completion_uses_configurable_short_timeout(monkeypatch) -> None:
    monkeypatch.setenv("BUDGETFLOW_LLM_TIMEOUT_S", "42")
    captured: dict = {}

    def fake_litellm_completion(**kwargs):
        captured.update(kwargs)
        return _Response()

    monkeypatch.setattr("budgetflow.adapter.mini_swe_proxy.litellm.completion", fake_litellm_completion)
    model, _ = _model("all_t3")

    model._completion(
        [{"role": "user", "content": "x"}],
        backend_name=TIER3_BACKEND,
        model_name="openai/gpt-5.4",
        model_kwargs={"api_key": "test", "api_base": "https://example.test"},
    )

    assert captured["timeout"] == 42.0
    assert "tools" in captured


def test_selected_backend_does_not_downgrade_on_reserve_failure(monkeypatch) -> None:
    monkeypatch.setattr("budgetflow.adapter.mini_swe_proxy.load_env_file", lambda: None)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test")
    monkeypatch.setenv("AICODE007_API_KEY", "test")
    model, _ = _model("value_aware_task_level")
    selected = next(b for b in model.routing.backends if b.name == TIER3_BACKEND)
    model.routing.task_level_backend = selected
    model.governor.state.total_budget = 0.000001
    model.governor.state.available_budget = 0.000001

    with pytest.raises(BudgetFlowBudgetError):
        model._reserve_backend(selected, input_tokens=1000)

    assert model.backend_picks == []
    assert model.last_exit_reason == "budget_exhausted"
