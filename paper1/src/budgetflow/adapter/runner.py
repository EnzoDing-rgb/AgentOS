from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
MINI_SWE_SRC = REPO_ROOT / "external" / "mini-swe-agent" / "src"
if str(MINI_SWE_SRC) not in sys.path:
    sys.path.insert(0, str(MINI_SWE_SRC))

from minisweagent.agents.default import DefaultAgent  # noqa: E402
from minisweagent.config import get_config_from_spec  # noqa: E402
from minisweagent.environments.local import LocalEnvironment  # noqa: E402
from minisweagent.exceptions import Submitted  # noqa: E402
from minisweagent.utils.serialize import recursive_merge  # noqa: E402

from ..governor import BudgetGovernor, GovernorConfig
from ..ledger import WorkflowLedgerStore
from ..lite_tasks import LiteTaskRecord
from ..local_harness import clone_or_checkout, evaluate_local_harness
from .backends import build_deepseek_backends
from .mini_swe_proxy import BudgetFlowLitellmModel
from .strategies import build_routing_context

SWEBENCH_CONFIG = REPO_ROOT / "external" / "mini-swe-agent" / "src" / "minisweagent" / "config" / "benchmarks" / "swebench.yaml"


@dataclass(frozen=True)
class MiniSweRunResult:
    instance_id: str
    strategy: str
    patch_text: str | None
    exit_status: str
    total_cost: float
    backend_picks: tuple[str, ...]
    llm_turns: int
    harness_resolved: bool
    harness_detail: str
    violations: tuple[str, ...]


def _load_agent_config() -> dict:
    config = recursive_merge(
        get_config_from_spec(SWEBENCH_CONFIG),
        {
            "agent": {
                "cost_limit": 0.0,
                "step_limit": 80,
                "confirm_exit": False,
            },
            "environment": {
                "timeout": 120,
            },
        },
    )
    return config


def run_mini_swe_task(
    task: LiteTaskRecord,
    *,
    strategy: str = "all_pro",
    budget_per_task: float | None = None,
    budget_pressure: float | None = None,
) -> MiniSweRunResult:
    repo_dir = clone_or_checkout(task)
    config = _load_agent_config()
    backends = build_deepseek_backends()
    ledger = WorkflowLedgerStore()
    cap = budget_per_task if budget_per_task is not None else 1_000_000.0
    governor = BudgetGovernor(
        GovernorConfig(total_budget=cap, default_max_output_tokens=4096),
        ledger,
    )
    routing = build_routing_context(strategy, backends, budget_pressure=budget_pressure)
    model_cfg = config.get("model", {})
    model = BudgetFlowLitellmModel(
        workflow_id=task.instance_id,
        governor=governor,
        routing=routing,
        observation_template=model_cfg.get("observation_template"),
        format_error_template=model_cfg.get("format_error_template"),
    )
    env = LocalEnvironment(cwd=str(repo_dir), timeout=config.get("environment", {}).get("timeout", 120))
    agent = DefaultAgent(model, env, **config.get("agent", {}))

    patch_text: str | None = None
    exit_status = "unknown"
    try:
        exit_info = agent.run(task.problem_statement)
        exit_status = str(exit_info.get("exit_status", "unknown"))
        patch_text = exit_info.get("submission") or None
    except Submitted as submitted:
        message = submitted.args[0] if submitted.args else {}
        exit_status = message.get("extra", {}).get("exit_status", "Submitted")
        patch_text = message.get("extra", {}).get("submission") or message.get("content")
    except Exception as exc:  # noqa: BLE001
        exit_status = type(exc).__name__

    harness = evaluate_local_harness(task, patch_text)
    violations: list[str] = []
    if governor.state.available_budget < 0:
        violations.append("budget_violation")
    return MiniSweRunResult(
        instance_id=task.instance_id,
        strategy=strategy,
        patch_text=patch_text,
        exit_status=exit_status,
        total_cost=governor.state.spent_budget,
        backend_picks=tuple(model.backend_picks),
        llm_turns=model.step_index,
        harness_resolved=harness.harness_resolved,
        harness_detail=harness.detail,
        violations=tuple(violations),
    )
