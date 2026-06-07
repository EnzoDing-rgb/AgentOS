"""Task and policy execution for compare runs."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from budgetflow.adaptive_routing import AdaptiveRoutingRegistry
from budgetflow.auto_budget import BudgetEstimate
from budgetflow.compare_checkpoint import CompareCheckpointStore, GlobalRunProgress, StrategyScoreboard
from budgetflow.experiments.compare_config import (
    CompareStrategy,
    fmt_usd,
    w_i_profile_for_record,
    workspace_key,
)
from budgetflow.experiments.compare_summary import _print_run_done
from budgetflow.failure_classification import build_forensic_summary, build_verdict, classify_failure
from budgetflow.governor import BudgetGovernor, GovernorConfig
from budgetflow.heartbeat import run_with_heartbeat
from budgetflow.ledger import WorkflowLedgerStore
from budgetflow.observability import build_observability_status, parse_harness_evidence
from budgetflow.run_guards import CompareRunGuards
from budgetflow.run_trace import TraceConsoleLevel
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
    return trimmed


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
    budget_estimate: BudgetEstimate | None = None,
    run_series: str = "",
    policy_lane: str = "",
    budget_mode: str = "shared",
    per_task_cap: float | None = None,
) -> dict:
    started = time.time()
    key = workspace_key(cfg, task.instance_id)
    adaptive = None
    if adaptive_registry is not None:
        adaptive = adaptive_registry.for_strategy(cfg.name, cfg.routing)
    if adaptive is not None:
        adaptive.reset_task_runtime()
        adaptive.set_task_context(task.instance_id)

    from budgetflow.adapter.runner import run_mini_swe_task

    task_value, _ = value_context.task_value(task.instance_id)
    result = run_mini_swe_task(
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
        task_value=task_value,
        median_task_value=value_context.median_task_value,
    )
    batch_snapshot = governor.budget_snapshot()
    record = {
        "instance_id": result.instance_id,
        "strategy": cfg.name,
        "routing": cfg.routing,
        "w_i_profile": w_i_profile_for_record(cfg.routing),
        "budget_tier": cfg.budget_tier or "uncapped",
        "batch_budget_cap": None if cfg.budget_tier is None else batch_budget_cap,
        "batch_spent": batch_snapshot.get("spent_budget"),
        "batch_available": batch_snapshot.get("available_budget"),
        "batch_snapshot": batch_snapshot,
        "task_cost": result.total_cost,
        "budget_spent": result.total_cost,
        "budget_available": batch_snapshot.get("available_budget"),
        "budget_snapshot": batch_snapshot,
        "task_index_in_batch": task_index,
        "workspace_key": key,
        "harness_resolved": result.harness_resolved,
        "resolved": result.harness_resolved,
        "patch_extracted": bool(result.patch_text),
        "patch_source": result.patch_source,
        "submitted_patch": result.submitted_patch_path,
        "exit_status": result.exit_status,
        "exit_reason": result.exit_reason,
        "total_cost": result.total_cost,
        "backend_picks": list(result.backend_picks),
        "llm_turns": result.llm_turns,
        "turns": result.llm_turns,
        "violations": list(result.violations),
        "detail": result.harness_detail,
        "agent_gold_edited": result.agent_gold_edited,
        "agent_gold_files": list(result.agent_gold_files),
        "agent_attempted_submit": result.agent_attempted_submit,
        "agent_submitted": result.agent_submitted,
        "prompt_tokens_total": result.prompt_tokens_total,
        "completion_tokens_total": result.completion_tokens_total,
        "elapsed_s": round(time.time() - started, 1),
        "agent_summary": {
            "gold_edited": result.agent_gold_edited,
            "gold_files": list(result.agent_gold_files),
            "attempted_submit": result.agent_attempted_submit,
            "submitted": result.agent_submitted,
        },
        "turn_trace_count": result.turn_trace_count,
        "turn_traces": truncate_turn_traces(result.turn_traces, trace_max_turns, trace_truncate_chars)
        if enable_turn_trace and result.turn_traces else None,
        "run_series": run_series,
        "policy_lane": policy_lane,
        "budget_mode": budget_mode,
        "per_task_cap": per_task_cap,
        "task_order_index": task_index,
        "task_features": {
            "patch_lines": len(str(getattr(task, "patch", "") or "").splitlines()),
            "f2p_count": len(getattr(task, "fail_to_pass", ()) or ()),
            "p2p_count": len(getattr(task, "pass_to_pass", ()) or ()),
            "problem_length": len(str(getattr(task, "problem_statement", "") or "")),
        },
        "row_started_at": started,
        "row_finished_at": time.time(),
        "attempt_id": f"{run_series}_{cfg.name}_{task.instance_id}" if run_series else "",
    }
    if adaptive is not None:
        prior = adaptive.prior_summary_for_trace()
        if prior:
            record["routing_prior_summary"] = prior
            record["policy_memory_enabled"] = True
        else:
            record["policy_memory_enabled"] = False
    elif adaptive_registry is not None and adaptive_registry.policy_memory is not None:
        prior = adaptive_registry.policy_memory.routing_prior_summary(task.instance_id)
        record["routing_prior_summary"] = prior
        record["policy_memory_enabled"] = True
    else:
        record["policy_memory_enabled"] = False

    record["failure_class"] = classify_failure(record)
    record["forensic_summary"] = build_forensic_summary(record)
    record["harness_evidence"] = parse_harness_evidence(str(record.get("detail") or "")).__dict__
    record["observability_status"] = build_observability_status(record)
    verdict = build_verdict(record)
    record["verdict_axis"] = verdict["verdict_axis"]
    record["failure_owner"] = verdict["failure_owner"]
    record["failure_stage"] = verdict["failure_stage"]
    record["failure_subtype"] = verdict.get("failure_subtype", "")
    record["evidence_complete"] = verdict["evidence_complete"]
    record["missing_evidence"] = verdict["missing_evidence"]

    if budget_estimate is not None:
        record["auto_budget_enabled"] = True
        record["estimated_task_cap"] = budget_estimate.cap
        record["estimated_task_cost"] = budget_estimate.estimated_cost
        record["budget_prior_source"] = budget_estimate.source
        record["budget_prior_confidence"] = budget_estimate.confidence
        record["budget_estimator_version"] = "v1"
        record["auto_budget_memory_used"] = budget_estimate.source.startswith("memory_")
        record["auto_budget_memory_neighbors"] = budget_estimate.memory_neighbors
        record["auto_budget_features"] = budget_estimate.features

    return record


def run_strategy_batch(
    cfg: CompareStrategy,
    tasks: list,
    *,
    batch_budget_cap: float,
    value_context: ValueEfficiencyContext,
    per_task_cap: float | None = None,
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
    task_caps: dict[str, float] | None = None,
    budget_estimates: dict[str, BudgetEstimate] | None = None,
    run_series: str = "",
    heartbeat_writer: object | None = None,
) -> tuple[list[dict], float]:
    def log(msg: str) -> None:
        if print_lock:
            with print_lock:
                print(msg, flush=True)
        else:
            print(msg, flush=True)

    use_per_task = cfg.budget_tier is not None and (
        (per_task_cap is not None and per_task_cap > 0) or (task_caps is not None)
    )
    ledger = WorkflowLedgerStore()
    governor: BudgetGovernor | None = None
    if not use_per_task:
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

    if use_per_task:
        cap_label = "auto_budget_per_task" if task_caps is not None else (
            f"per_task_cap={fmt_usd(per_task_cap)}" if per_task_cap else "per_task"
        )
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
    for task_index, task in enumerate(tasks, start=1):
        if run_guards is not None and run_guards.is_strategy_halted(cfg.name):
            log(f"[guard] skip strategy={cfg.name} task={task.instance_id} (policy halted)")
            continue
        if run_guards is not None and run_guards.is_aborted():
            log(f"[guard] skip strategy={cfg.name} (global halt: {run_guards.abort_reason()})")
            break

        global_progress.start_task()
        if checkpoint is not None:
            cap_for_ckpt = per_task_cap if use_per_task and per_task_cap else batch_budget_cap
            checkpoint.mark_in_flight(cfg.name, task.instance_id, cap_for_ckpt)
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
                    f"regret={prior_summary.get('full_vs_tight_regret', 0):.3f} "
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
            if cfg.budget_tier is not None:
                if task_caps is not None:
                    task_cap = task_caps.get(task.instance_id)
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
                effective_batch_cap = task_governor.state.total_budget
            assert task_governor is not None
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
                budget_pressure=budget_pressure,
                pressure_max=pressure_max,
                adaptive_registry=adaptive_registry,
                enable_turn_trace=enable_turn_trace,
                trace_max_turns=trace_max_turns,
                trace_truncate_chars=trace_truncate_chars,
                budget_estimate=budget_estimates.get(task.instance_id) if budget_estimates else None,
                run_series=run_series,
                policy_lane=cfg.name,
                budget_mode="per_task_cap" if task_cap is not None else "shared",
                per_task_cap=task_cap,
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
        records.append(record)
        if checkpoint is not None:
            task_spent = float(record.get("task_cost") or record.get("total_cost") or 0)
            checkpoint.mark_task_done(
                cfg.name,
                task.instance_id,
                batch_spent=task_spent if use_per_task else float(governor.state.spent_budget),
                batch_cap=per_task_cap if use_per_task else batch_budget_cap,
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

    if use_per_task:
        batch_spent_total = sum(float(r.get("task_cost") or r.get("total_cost") or 0) for r in records)
    else:
        assert governor is not None
        batch_spent_total = governor.state.spent_budget
    return records, batch_spent_total
