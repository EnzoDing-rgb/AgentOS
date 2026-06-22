"""Task and policy execution for compare runs."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from budgetflow.adaptive_routing import AdaptiveRoutingRegistry
from budgetflow.adapters import (
    SwebenchProgressAdapter,
    SwebenchTaskAdapter,
)
from budgetflow.adapter import runner as mini_swe_runner
from budgetflow.adapter.stall_guard import stall_guard_enabled
from budgetflow.allocation import AllocationContext
from budgetflow.frozen_router import FrozenRouterPlan
from budgetflow.compare_checkpoint import CompareCheckpointStore, GlobalRunProgress, StrategyScoreboard
from budgetflow.experiments.compare_config import (
    CompareStrategy,
    fmt_usd,
    w_i_profile_for_record,
    workspace_key,
)
from budgetflow.experiments.compare_setup import BUDGETFLOW_ACTIVE_ROUTINGS, PLANNED_TASK_BUDGET_MODE
from budgetflow.experiments.compare_summary import _print_run_done
from budgetflow.failure_classification import (
    EXIT_OWNER_BUDGET_EXHAUSTED,
    build_forensic_summary,
    build_score_status,
    build_verdict,
    classify_failure,
    compute_exit_owner,
)
from budgetflow.governor import BudgetGovernor, GovernorConfig
from budgetflow.heartbeat import run_with_heartbeat
from budgetflow.ledger import WorkflowLedgerStore
from budgetflow.observability import build_observability_status, parse_harness_evidence
from budgetflow.observability import build_harness_trust
from budgetflow.planned_task_budget import effective_planned_task_cap
from budgetflow.run_guards import CompareRunGuards
from budgetflow.run_trace import TraceConsoleLevel
from budgetflow.types import WorkflowSegment
from budgetflow.value_efficiency import ValueEfficiencyContext


def truncate_turn_traces(
    traces: list[dict] | None, max_turns: int, max_chars: int
) -> list[dict] | None:
    if traces is None:
        return None
    trimmed = traces[-max_turns:] if len(traces) > max_turns else traces
    for trace in trimmed:
        digest = trace.get("bash_digest")
        if isinstance(digest, str) and len(digest) > max_chars:
            trace["bash_digest"] = digest[:max_chars]
        action_digest = trace.get("action_digest")
        if isinstance(action_digest, str) and len(action_digest) > max_chars:
            trace["action_digest"] = action_digest[:max_chars]
    return trimmed


def _effective_planned_task_cap(
    *,
    planned_task_caps: dict[str, float],
    remaining_task_ids: list[str],
    task_id: str,
    batch_budget_cap: float,
    shared_spent: float,
) -> float | None:
    return effective_planned_task_cap(
        planned_task_caps=planned_task_caps,
        remaining_task_ids=remaining_task_ids,
        task_id=task_id,
        batch_budget_cap=batch_budget_cap,
        shared_spent=shared_spent,
    )


def _remaining_task_ids_for_planned_cap(
    *,
    selected_task_ids: list[str],
    task_index: int,
    task_id: str,
    planned_task_order: list[str] | None,
    planned_rebalance_task_limit: int | None,
) -> list[str]:
    """Return the remaining demand set used for planned-task cap clipping."""
    current_remaining = list(selected_task_ids[max(0, task_index - 1):])
    if not planned_task_order or not planned_rebalance_task_limit:
        return current_remaining

    rebalance_order = list(planned_task_order[:max(0, int(planned_rebalance_task_limit))])
    if task_id not in rebalance_order:
        return []
    current_remaining_set = set(current_remaining)
    return [remaining_id for remaining_id in rebalance_order if remaining_id in current_remaining_set]


def _shared_batch_pressure(
    *,
    batch_budget_cap: float,
    shared_spent: float,
    init: float | None,
    pressure_max: float | None,
) -> float | None:
    if init is None:
        return None
    if batch_budget_cap <= 0:
        return init
    ceiling = pressure_max if pressure_max is not None else init
    used = min(1.0, max(0.0, float(shared_spent) / float(batch_budget_cap)))
    return init + used * (ceiling - init)


def run_task_record(
    task,
    *,
    cfg: CompareStrategy,
    batch_budget_cap: float,
    governor: BudgetGovernor,
    ledger: WorkflowLedgerStore,
    task_index: int,
    step_limit: int,
    value_context: ValueEfficiencyContext,
    trace_console: TraceConsoleLevel = "quiet",
    progress_box: dict[str, str] | None = None,
    budget_pressure: float | None = None,
    pressure_max: float | None = None,
    adaptive_registry: AdaptiveRoutingRegistry | None = None,
    enable_turn_trace: bool = False,
    trace_max_turns: int = 200,
    trace_truncate_chars: int = 120,
    run_series: str = "",
    policy_lane: str = "",
    budget_mode: str = "shared",
    per_task_cap: float | None = None,
    budget_plan_task_cap: float | None = None,
    planned_task_budget_source: str | None = None,
    budget_input: dict[str, Any] | None = None,
    task_set: str = "",
    task_set_kind: str = "",
    frozen_plan: FrozenRouterPlan | None = None,
    calibrated_model_fit: dict[str, float] | None = None,
    calibrated_model_fit_source: str = "catalog_progress_prior",
    calibrated_model_fit_confidence: str = "none",
) -> dict:
    started = time.time()
    task_adapter = SwebenchTaskAdapter()
    progress_adapter = SwebenchProgressAdapter()
    instance_id = task_adapter.instance_id(task)
    task_features = task_adapter.features(task).as_record()
    key = workspace_key(cfg, instance_id)
    adaptive = None
    if adaptive_registry is not None:
        adaptive = adaptive_registry.for_strategy(cfg.name, cfg.routing)
    if adaptive is not None:
        adaptive.reset_task_runtime()
        adaptive.set_task_context(instance_id)

    task_value, value_source = value_context.task_value(instance_id)
    task_effort, effort_source = value_context.task_effort(instance_id)

    model_fit: dict[str, float] | None = (
        dict(calibrated_model_fit) if calibrated_model_fit else None
    )
    model_fit_source = (
        calibrated_model_fit_source if model_fit else "catalog_progress_prior"
    )
    budget_source = (
        planned_task_budget_source
        if planned_task_budget_source
        else "shared_batch_hard_budget"
    )

    allocation = AllocationContext(
        task_value=task_value,
        task_effort=task_effort,
        model_fit=model_fit,
        value_source=value_source,
        effort_source=effort_source,
        model_fit_source=model_fit_source,
        budget_source=budget_source,
        planned_task_budget=(
            budget_plan_task_cap
            if budget_plan_task_cap is not None and budget_plan_task_cap >= 0
            else per_task_cap if per_task_cap is not None and per_task_cap >= 0 else None
        ),
        effective_task_budget=per_task_cap if per_task_cap is not None and per_task_cap >= 0 else None,
        confidence={"model_fit": calibrated_model_fit_confidence},
    )
    result = mini_swe_runner.run_mini_swe_task(
        task,
        strategy=cfg.routing,
        strategy_label=cfg.name,
        step_limit=step_limit,
        trace_console=trace_console,
        progress_box=progress_box,
        agent_heartbeat=False,
        governor=governor,
        ledger=ledger,
        workspace_key=key,
        budget_pressure=budget_pressure,
        pressure_max=pressure_max,
        adaptive=adaptive,
        enable_turn_trace=enable_turn_trace,
        median_task_value=value_context.median_task_value,
        frozen_plan=frozen_plan,
        allocation=allocation,
        run_series=run_series,
    )
    outcome = progress_adapter.outcome_from_result(result)
    batch_snapshot = governor.budget_snapshot()
    record = {
        "instance_id": result.instance_id,
        "strategy": cfg.name,
        "routing": cfg.routing,
        "w_i_profile": w_i_profile_for_record(cfg.routing),
        "budget_scope": "shared_hard_budget" if cfg.budgeted else "unconstrained_diagnostic",
        "batch_budget_cap": batch_budget_cap if cfg.budgeted else None,
        "budget_input": dict(budget_input) if budget_input is not None else None,
        "batch_spent": batch_snapshot.get("spent_budget"),
        "batch_available": batch_snapshot.get("available_budget"),
        "batch_snapshot": batch_snapshot,
        "budget_spent": result.total_cost,
        "budget_available": batch_snapshot.get("available_budget"),
        "budget_snapshot": batch_snapshot,
        "task_index_in_batch": task_index,
        "workspace_key": key,
        **outcome.as_record(),
        "exit_status": result.exit_status,
        "exit_reason": result.exit_reason,
        "agent_exit_status": result.agent_exit_status,
        "agent_exit_reason": result.agent_exit_reason,
        "total_cost": result.total_cost,
        "backend_picks": list(result.backend_picks),
        "llm_turns": result.llm_turns,
        "violations": list(result.violations),
        "agent_gold_edited": result.agent_gold_edited,
        "agent_gold_files": list(result.agent_gold_files),
        "agent_attempted_submit": result.agent_attempted_submit,
        "agent_submitted": result.agent_submitted,
        "agent_environment_issues": list(getattr(result, "agent_environment_issues", ()) or ()),
        "prompt_tokens_total": result.prompt_tokens_total,
        "completion_tokens_total": result.completion_tokens_total,
        "provider_usage_turns": result.provider_usage_turns,
        "estimated_usage_turns": result.estimated_usage_turns,
        "usage_source": result.usage_source,
        "cost_mode": result.cost_mode,
        "elapsed_s": round(time.time() - started, 1),
        "agent_summary": {
            "gold_edited": result.agent_gold_edited,
            "gold_files": list(result.agent_gold_files),
            "attempted_submit": result.agent_attempted_submit,
            "submitted": result.agent_submitted,
            "agent_environment_issues": list(getattr(result, "agent_environment_issues", ()) or ()),
        },
        "turn_trace_count": result.turn_trace_count,
        "trace_dir": result.trace_dir,
        "trace_steps": result.trace_steps_path,
        "turn_traces": truncate_turn_traces(result.turn_traces, trace_max_turns, trace_truncate_chars)
        if enable_turn_trace and result.turn_traces else None,
        "run_series": run_series,
        "policy_lane": policy_lane,
        "budget_mode": budget_mode,
        "per_task_cap": per_task_cap,
        "budget_plan_task_cap": budget_plan_task_cap,
        "planned_task_budget_source": planned_task_budget_source,
        "task_order_index": task_index,
        "task_features": task_features,
        "task_set": task_set,
        "task_set_kind": task_set_kind,
        "row_started_at": started,
        "row_finished_at": time.time(),
        "attempt_id": f"{run_series}_{cfg.name}_{instance_id}" if run_series else "",
    }
    record["model_fit_source"] = model_fit_source
    record["model_fit_confidence"] = calibrated_model_fit_confidence if model_fit else "none"
    record["model_fit_active"] = allocation.has_trusted_model_fit
    record["exit_owner"] = compute_exit_owner(record)
    record["budget_exhausted"] = record["exit_owner"] == EXIT_OWNER_BUDGET_EXHAUSTED
    record["stall_guard_owner"] = "budgetflow" if stall_guard_enabled(cfg.routing) else "none"
    record["protocol_retry_used"] = result.protocol_retry_used
    record["protocol_retry_success"] = result.protocol_retry_success
    record["protocol_retry_reason"] = result.protocol_retry_reason
    record["protocol_retry_attempts"] = result.protocol_retry_attempts
    record["protocol_retry_limit"] = result.protocol_retry_limit
    record["protocol"] = result.protocol
    record["parser"] = result.parser
    record["provider_error_kind"] = result.provider_error_kind
    record["provider_retryable"] = result.provider_retryable
    if adaptive is not None:
        prior = adaptive.prior_summary_for_trace()
        record["memory_mode"] = getattr(adaptive, "memory_mode", "off")
        if prior:
            record["routing_prior_summary"] = prior
            record["routing_prior_segment"] = WorkflowSegment.CONTEXT
            if adaptive_registry is not None and adaptive_registry.policy_memory is not None:
                record["routing_repair_prior_summary"] = adaptive_registry.policy_memory.routing_prior_summary(
                    instance_id,
                    WorkflowSegment.ACTION,
                )
                record["routing_repair_prior_segment"] = WorkflowSegment.ACTION
            record["policy_memory_enabled"] = True
        else:
            record["policy_memory_enabled"] = False
        if adaptive_registry is not None:
            record["learn_policy_input_views"] = list(adaptive_registry.learn_policy_inputs.active_views)
    elif adaptive_registry is not None and adaptive_registry.policy_memory is not None:
        prior = adaptive_registry.policy_memory.routing_prior_summary(instance_id)
        record["routing_prior_summary"] = prior
        record["policy_memory_enabled"] = True
        record["memory_mode"] = getattr(adaptive_registry, "memory_mode", "built_in")
        record["learn_policy_input_views"] = list(adaptive_registry.learn_policy_inputs.active_views)
    else:
        record["policy_memory_enabled"] = False
        record["memory_mode"] = "off"
        record["learn_policy_input_views"] = []

    # Frozen router plan audit fields.
    if frozen_plan is not None:
        record.update(frozen_plan.as_jsonl_record(instance_id))
    else:
        record["frozen_plan_name"] = None
        record["frozen_plan_preferred_model"] = None
        record["frozen_plan_priority"] = None

    record["failure_class"] = classify_failure(record)
    record["forensic_summary"] = build_forensic_summary(record)
    record["harness_evidence"] = parse_harness_evidence(str(record.get("detail") or "")).__dict__
    record["observability_status"] = build_observability_status(record)
    harness_trust = build_harness_trust(record)
    record["harness_trust"] = harness_trust["harness_trust"]
    record["harness_issues"] = harness_trust["harness_issues"]
    record["harness_owner"] = harness_trust["harness_owner"]
    record["harness_severity"] = harness_trust["severity"]
    verdict = build_verdict(record)
    record["verdict_axis"] = verdict["verdict_axis"]
    record["failure_owner"] = verdict["failure_owner"]
    record["failure_stage"] = verdict["failure_stage"]
    record["failure_subtype"] = verdict.get("failure_subtype", "")
    record["evidence_complete"] = verdict["evidence_complete"]
    record["missing_evidence"] = verdict["missing_evidence"]
    record.update(build_score_status(record))

    return record


def run_strategy_batch(
    cfg: CompareStrategy,
    tasks: list,
    *,
    batch_budget_cap: float,
    value_context: ValueEfficiencyContext,
    per_task_cap: float | None = None,
    planned_task_caps: dict[str, float] | None = None,
    planned_task_order: list[str] | None = None,
    planned_rebalance_task_limit: int | None = None,
    planned_task_budget_source: str = "budget_plan:planned_task_budget_by_strategy",
    soft_budget: float | None = None,
    max_overrun: float = 0.0,
    step_limit: int,
    trace_console: TraceConsoleLevel,
    heartbeat: float,
    global_progress: GlobalRunProgress,
    scoreboard: StrategyScoreboard | None,
    print_lock: threading.Lock | None,
    budget_pressure: float | None = None,
    pressure_max: float | None = None,
    initial_spent: float = 0.0,
    checkpoint: CompareCheckpointStore | None = None,
    on_task_complete: Callable[[dict], None] | None = None,
    run_guards: CompareRunGuards | None = None,
    adaptive_registry: AdaptiveRoutingRegistry | None = None,
    enable_turn_trace: bool = False,
    trace_max_turns: int = 200,
    trace_truncate_chars: int = 120,
    budget_input: dict[str, Any] | None = None,
    run_series: str = "",
    heartbeat_writer: object | None = None,
    task_set: str = "",
    task_set_kind: str = "",
    frozen_plan: FrozenRouterPlan | None = None,
    budget_mode: str | None = None,
    calibrated_model_fit: dict[str, float] | None = None,
    calibrated_model_fit_source: str = "catalog_progress_prior",
    calibrated_model_fit_confidence: str = "none",
) -> tuple[list[dict], float]:
    def log(msg: str) -> None:
        if print_lock:
            with print_lock:
                print(msg, flush=True)
        else:
            print(msg, flush=True)

    planned_task_caps = {
        str(task_id): float(cap)
        for task_id, cap in (planned_task_caps or {}).items()
        if cap is not None and float(cap) > 0
    }
    use_planned_task_caps = (
        cfg.budgeted
        and cfg.routing in BUDGETFLOW_ACTIVE_ROUTINGS
        and budget_mode == PLANNED_TASK_BUDGET_MODE
    )
    if (
        cfg.budgeted
        and budget_mode == PLANNED_TASK_BUDGET_MODE
        and cfg.routing not in BUDGETFLOW_ACTIVE_ROUTINGS
    ):
        raise SystemExit(f"{PLANNED_TASK_BUDGET_MODE} is only valid for BudgetFlow active policies")
    if use_planned_task_caps and not planned_task_caps:
        raise SystemExit(f"{cfg.name} uses {PLANNED_TASK_BUDGET_MODE} but no planned task budgets were provided")
    use_planned_task_caps = (
        use_planned_task_caps
        and bool(planned_task_caps)
    )
    use_per_task = (
        cfg.budgeted
        and not use_planned_task_caps
        and per_task_cap is not None
        and per_task_cap > 0
    )
    shared_spent = max(0.0, float(initial_spent or 0.0))
    ledger = WorkflowLedgerStore()
    governor: BudgetGovernor | None = None
    if not use_per_task and not use_planned_task_caps:
        governor = BudgetGovernor(
            GovernorConfig(
                total_budget=batch_budget_cap,
                default_max_output_tokens=4096,
                soft_budget=soft_budget,
                max_overrun=max_overrun if soft_budget is not None else 0.0,
            ),
            ledger,
        )
        if initial_spent > 0:
            governor.state.spent_budget = initial_spent
            governor.state.available_budget = max(0.0, governor.state.total_budget - initial_spent)

    if use_planned_task_caps:
        cap_label = f"planned_task_budget tasks={len(planned_task_caps)} shared_cap={fmt_usd(batch_budget_cap)}"
    elif use_per_task:
        cap_label = f"per_task_cap={fmt_usd(per_task_cap)}" if per_task_cap else "per_task"
        if max_overrun > 0:
            cap_label += f"+overrun={fmt_usd(max_overrun)}"
    else:
        cap_label = f"shared_cap={fmt_usd(batch_budget_cap)}"
        if soft_budget is not None:
            cap_label += f" soft={fmt_usd(soft_budget)}+overrun={fmt_usd(max_overrun)}"
    log(
        f"[batch] strategy={cfg.name} tasks={len(tasks)} "
        f"{cap_label} spent_resume={fmt_usd(initial_spent)} mode=serial_tasks"
    )

    records: list[dict] = []
    selected_task_ids = [str(task.instance_id) for task in tasks]
    if use_planned_task_caps:
        missing_caps = [task_id for task_id in selected_task_ids if task_id not in planned_task_caps]
        if missing_caps:
            preview = ", ".join(missing_caps[:8])
            suffix = "" if len(missing_caps) <= 8 else f", ... +{len(missing_caps) - 8} more"
            raise SystemExit(
                f"{cfg.name} uses {PLANNED_TASK_BUDGET_MODE} but budget plan is missing "
                f"planned task budgets for: {preview}{suffix}"
            )
    for task_index, task in enumerate(tasks, start=1):
        if run_guards is not None and run_guards.is_strategy_halted(cfg.name):
            log(f"[guard] skip strategy={cfg.name} task={task.instance_id} (policy halted)")
            continue
        if run_guards is not None and run_guards.is_aborted():
            log(f"[guard] skip strategy={cfg.name} (global halt: {run_guards.abort_reason()})")
            break

        global_progress.start_task()
        if checkpoint is not None:
            checkpoint.mark_in_flight(cfg.name, task.instance_id, batch_budget_cap)
        banner = global_progress.format_banner(scoreboard)
        log(f"\n======== {banner} ========\n[start] task={task.instance_id} strategy={cfg.name}")

        status_box: dict[str, str] = {
            "phase": "prep",
            "status": f"strategy={cfg.name} task={task.instance_id} prep",
        }
        label = f"{cfg.name} {task.instance_id}"

        def status() -> str:
            base = status_box.get("status", f"strategy={cfg.name} phase={status_box['phase']}")
            return f"{global_progress.format_global(scoreboard)} | {base}"

        def execute() -> dict:
            status_box["phase"] = "agent"
            pm = adaptive_registry.policy_memory if adaptive_registry is not None else None
            if pm is not None and cfg.routing != "all_pro":
                prior_summary = pm.routing_prior_summary(task.instance_id)
                prior_snippet = (
                    f"prior_action={prior_summary.get('learned_action', 'default')} "
                    f"esc={prior_summary.get('value_triggered_escalation_action', 'default')}"
                    f"/w={prior_summary.get('value_triggered_escalation_window', '?')} "
                    f"regret={prior_summary.get('full_vs_baseline_regret', 0):.3f} "
                    f"task_seen={prior_summary.get('task_seen', '?')}"
                )
            elif cfg.routing == "all_pro":
                prior_snippet = "prior=off(all_pro)"
            else:
                prior_snippet = "prior=off"
            status_box["status"] = f"strategy={cfg.name} task={task.instance_id} {prior_snippet}"

            task_governor = governor
            task_ledger = ledger
            effective_batch_cap = batch_budget_cap
            task_cap: float | None = None
            budget_plan_task_cap: float | None = None
            if cfg.budgeted:
                if use_planned_task_caps:
                    raw_planned_cap = planned_task_caps.get(str(task.instance_id))
                    if raw_planned_cap is not None and raw_planned_cap > 0:
                        budget_plan_task_cap = float(raw_planned_cap)
                    task_cap = _effective_planned_task_cap(
                        planned_task_caps=planned_task_caps,
                        remaining_task_ids=_remaining_task_ids_for_planned_cap(
                            selected_task_ids=selected_task_ids,
                            task_index=task_index,
                            task_id=str(task.instance_id),
                            planned_task_order=planned_task_order,
                            planned_rebalance_task_limit=planned_rebalance_task_limit,
                        ),
                        task_id=str(task.instance_id),
                        batch_budget_cap=batch_budget_cap,
                        shared_spent=shared_spent,
                    )
                elif per_task_cap is not None and per_task_cap > 0:
                    task_cap = per_task_cap
            if task_cap is not None:
                task_ledger = WorkflowLedgerStore()
                task_governor = BudgetGovernor(
                    GovernorConfig(
                        total_budget=task_cap,
                        default_max_output_tokens=4096,
                        soft_budget=task_cap if max_overrun > 0 else None,
                        max_overrun=max_overrun,
                    ),
                    task_ledger,
                )
                effective_batch_cap = batch_budget_cap
            assert task_governor is not None
            task_budget_pressure = (
                _shared_batch_pressure(
                    batch_budget_cap=batch_budget_cap,
                    shared_spent=shared_spent,
                    init=budget_pressure,
                    pressure_max=pressure_max,
                )
                if use_planned_task_caps
                else budget_pressure
            )
            return run_task_record(
                task,
                cfg=cfg,
                batch_budget_cap=effective_batch_cap,
                governor=task_governor,
                ledger=task_ledger,
                task_index=task_index,
                step_limit=step_limit,
                value_context=value_context,
                trace_console=trace_console,
                progress_box=status_box,
                budget_pressure=task_budget_pressure,
                pressure_max=pressure_max,
                adaptive_registry=adaptive_registry,
                enable_turn_trace=enable_turn_trace,
                trace_max_turns=trace_max_turns,
                trace_truncate_chars=trace_truncate_chars,
                budget_input=budget_input,
                run_series=run_series,
                policy_lane=cfg.name,
                budget_mode=budget_mode
                or (
                    "per_task_cap" if task_cap is not None
                    else "shared"
                ),
                per_task_cap=task_cap,
                budget_plan_task_cap=budget_plan_task_cap,
                planned_task_budget_source=(
                    planned_task_budget_source
                    if use_planned_task_caps and task_cap is not None
                    else None
                ),
                task_set=task_set,
                task_set_kind=task_set_kind,
                frozen_plan=frozen_plan,
                calibrated_model_fit=calibrated_model_fit,
                calibrated_model_fit_source=calibrated_model_fit_source,
                calibrated_model_fit_confidence=calibrated_model_fit_confidence,
            )

        try:
            if heartbeat > 0:
                on_beat = None
                if heartbeat_writer is not None:
                    task_started = time.time()

                    def beat() -> None:
                        _total, rows, _running = global_progress.snapshot()
                        heartbeat_writer.pulse(
                            rows_done=rows,
                            active_strategy=str(cfg.name),
                            active_instance=str(task.instance_id),
                            active_elapsed_s=time.time() - task_started,
                        )

                    on_beat = beat
                record = run_with_heartbeat(
                    label, execute, interval_s=heartbeat, status_fn=status, on_beat=on_beat,
                )
            else:
                record = execute()
        finally:
            done_n = global_progress.finish_task()

        if print_lock:
            with print_lock:
                _print_run_done(record, done=done_n, total=global_progress.total, strategy=cfg.name)
        else:
            _print_run_done(record, done=done_n, total=global_progress.total, strategy=cfg.name)
        if use_planned_task_caps:
            task_spent = float(record.get("total_cost") or 0.0)
            shared_spent = min(float(batch_budget_cap), shared_spent + task_spent)
            record["batch_budget_cap"] = batch_budget_cap
            record["batch_spent"] = shared_spent
            record["batch_available"] = max(0.0, float(batch_budget_cap) - shared_spent)
            record["batch_snapshot"] = {
                "total_budget": batch_budget_cap,
                "soft_budget": batch_budget_cap,
                "absolute_budget": batch_budget_cap,
                "max_overrun": 0.0,
                "available_budget": record["batch_available"],
                "reserved_budget": 0.0,
                "spent_budget": shared_spent,
            }
        records.append(record)
        if checkpoint is not None:
            task_spent = float(record.get("total_cost") or 0)
            score_status = str(record.get("score_status") or "")
            checkpoint.mark_task_done(
                cfg.name,
                task.instance_id,
                batch_spent=(
                    shared_spent
                    if use_planned_task_caps
                    else task_spent if use_per_task
                    else float(governor.state.spent_budget)
                ),
                batch_cap=(
                    batch_budget_cap
                ),
                completed=score_status in {"pass", "true_fail"},
            )
        if on_task_complete is not None:
            on_task_complete(record)
        if adaptive_registry is not None:
            adaptive_registry.record_task(cfg.name, cfg.routing, record)

        if run_guards is not None:
            action = run_guards.record_task(record)
            run_guards.log_action(action)
            if action.halt_all or action.halt_strategy:
                break

    if use_planned_task_caps:
        batch_spent_total = shared_spent
    elif use_per_task:
        batch_spent_total = sum(float(r.get("total_cost") or 0) for r in records)
    else:
        assert governor is not None
        batch_spent_total = governor.state.spent_budget
    return records, batch_spent_total
