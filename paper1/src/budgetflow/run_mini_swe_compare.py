"""Compare N tasks × strategies: shared batch budget per policy.

Each policy runs its task list serially on one BudgetGovernor (shared pool).
Different policies may run in parallel (--jobs) using git worktrees for repo isolation.

Usage (from paper1/):
  # fast smoke (default 3 tasks)
  PYTHONPATH=src:../external/mini-swe-agent/src python -u -m budgetflow.run_mini_swe_compare --preset 3x3 --jobs 3
  # paper mainline compare uses docs/config/paper_mainline_strategies.v1.json
  PYTHONPATH=src:../external/mini-swe-agent/src python -u -m budgetflow.run_mini_swe_compare --ids <ids> --jobs 6

Outputs:
  data/runs/<run_series>-N.jsonl
  data/runs/<run_series>-N.summary.log
"""

from __future__ import annotations

import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent

# Resolve mini-swe-agent via runtime module (handles env var / repo / fallback).
from budgetflow.runtime import resolve_mini_swe_src  # noqa: E402

MINI_SWE_SRC = resolve_mini_swe_src()
for path in (str(SRC), str(MINI_SWE_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from budgetflow.compare_checkpoint import (  # noqa: E402
    CompareCheckpointStore,
    GlobalRunProgress,
    StrategyScoreboard,
    checkpoint_path_for,
)
from budgetflow.console_log import dim, tag  # noqa: E402
from budgetflow.catalog_preflight import print_tier_catalog_preflight  # noqa: E402
from budgetflow.defaults import active_w_i_profile_name  # noqa: E402
from budgetflow.model_tiers import load_env_file  # noqa: E402
from budgetflow.experiments.compare_config import (  # noqa: E402
    CompareStrategy,
    batch_budget_cap as _batch_budget_cap,
    normalize_strategy as _normalize_strategy,
    required_backends_for_strategies as _required_backends_for_strategies,
    task_descriptor as _task_descriptor,
    task_set_kind as _task_set_kind,
)
from budgetflow.adapters import SwebenchBudgetAdapter  # noqa: E402
from budgetflow.experiments.compare_cli import parse_compare_args  # noqa: E402
from budgetflow.experiments.compare_memory import (  # noqa: E402
    run_policy_memory_gate_only,
)
from budgetflow.experiments.compare_readiness import (  # noqa: E402
    build_compare_readiness_report,
    format_readiness_report,
)
from budgetflow.experiments.compare_setup import (  # noqa: E402
    build_batch_budget_modes,
    calibrated_model_fit_from_budget_plan,
    load_tasks_for_compare,
    resolve_budget_plan,
    resolve_task_count,
    select_strategies,
    select_stage_batch_tasks,
    trace_console_from_args,
    validate_paper_mainline_budget_contract,
)
from budgetflow.experiments.compare_persistence import (  # noqa: E402
    CompareRunState,
    completed_keys as _completed_keys,
    ingest_batch_footer as _ingest_batch_footer,
    persist_task_record as _persist_task_record,
    rebuild_state_from_jsonl as _rebuild_state_from_jsonl,
    write_summary_snapshot as _write_summary_snapshot,
)
from budgetflow.experiments.compare_execution import run_strategy_batch  # noqa: E402
from budgetflow.experiments.compare_summary import (  # noqa: E402
    _format_strategy_totals,
)
from budgetflow.frozen_router import load_frozen_plan  # noqa: E402
from budgetflow.observability import (  # noqa: E402
    HeartbeatWriter,
)
from budgetflow.official_harness_crosscheck import build_crosscheck_artifacts  # noqa: E402
from budgetflow.learning_context import load_policy_memory_context  # noqa: E402
from budgetflow.adaptive_routing import AdaptiveRoutingRegistry  # noqa: E402
from budgetflow.run_guards import CompareRunGuards, set_active_guard  # noqa: E402
from budgetflow.run_series import release_run_identity, resolve_run_identity, scoreable_spend_by_strategy  # noqa: E402
from budgetflow.run_series import validate_resume_contract  # noqa: E402
from budgetflow.run_trace import TraceConsoleLevel  # noqa: E402
from budgetflow.runtime import check_cwd, is_nfs_or_banned, print_runtime_info, resolve_runtime_root, set_runtime_root  # noqa: E402
from budgetflow.value_efficiency import ValueEfficiencyContext  # noqa: E402

RUNS_DIR = REPO_ROOT / "data" / "runs"


def _compare_paths(tasks_n: int, strategies_n: int, *, stem: str | None = None) -> tuple[Path, Path]:
    base = stem or f"compare_{tasks_n}x{strategies_n}"
    return RUNS_DIR / f"{base}.jsonl", RUNS_DIR / f"{base}.summary.log"


def main() -> None:
    load_env_file()
    if not os.environ.get("NO_COLOR"):
        os.environ.setdefault("FORCE_COLOR", "1")
    args = parse_compare_args()

    # ── Gate-only: load PolicyMemory, validate, print summary, exit ────────
    # Must run BEFORE any provider check, output file creation, heartbeat, or
    # strategy loading. Gate-only makes zero API calls.
    if args.policy_memory_gate_only:
        sys.exit(run_policy_memory_gate_only(args, repo_root=REPO_ROOT))

    # ── Value observability: init before any tasks run ───────────────────
    if args.value_profile != "equal" and not args.value_matrix:
        print(
            f"[value_observability] FATAL: --value-profile={args.value_profile} requires "
            f"--value-matrix. Only --value-profile=equal can use default values.",
            flush=True,
        )
        sys.exit(2)
    value_context = ValueEfficiencyContext()
    value_context.init(
        value_profile=args.value_profile,
        value_matrix_path=args.value_matrix,
        value_source_kind=args.value_source_kind,
    )

    def enrich_record_with_value(record: dict) -> dict:
        return value_context.enrich_record(record)

    def enrich_record_final(record: dict) -> dict:
        """Enrich record with value, memory filtering, catalog provenance, frontier, and budget binding."""
        record = enrich_record_with_value(record)
        if policy_memory is not None:
            record["memory_filtering"] = policy_memory.memory_filtering_summary
        record["catalog"] = _catalog_source_info()
        if _frontier is not None:
            record["tier_frontier"] = _frontier.to_dict()
        if _budget_plan_data is not None:
            record["budget_plan"] = _budget_plan_data
        return record

    if value_context.lookup is None and args.value_profile != "equal":
        print(
            f"[value_observability] FATAL: profile '{args.value_profile}' not found "
            f"in value matrix {args.value_matrix}. Task values cannot be assigned. "
            f"Use --value-profile=equal for default values.",
            flush=True,
        )
        sys.exit(2)

    # ── Runtime root: set before any path-dependent operations ────────────
    if args.runtime_root:
        set_runtime_root(args.runtime_root, allow_nfs=args.allow_nfs_runtime)
    elif os.environ.get("BUDGETFLOW_RUNTIME_ROOT"):
        set_runtime_root(os.environ["BUDGETFLOW_RUNTIME_ROOT"], allow_nfs=args.allow_nfs_runtime)
    else:
        # Resolve default; fail-fast if default resolves to /Lishun.
        root, _ = resolve_runtime_root()
        if not args.allow_nfs_runtime and is_nfs_or_banned(root):
            raise SystemExit(
                f"RUNTIME CONFIG ERROR: default runtime root resolves to banned /Lishun path: {root}\n"
                f"  Use --runtime-root /tmp/budgetflow-runtime or set BUDGETFLOW_RUNTIME_ROOT.\n"
                f"  Or pass --allow-nfs-runtime to bypass this safety check."
            )

    check_cwd()

    if args.w_profile:
        os.environ["BF_W_PROFILE"] = args.w_profile
    if args.resume:
        args.append = True
        args.skip_completed = True
    if args.max_tasks_per_strategy is not None and args.max_tasks_per_strategy <= 0:
        raise SystemExit("--max-tasks-per-strategy must be a positive integer")

    tasks_n = resolve_task_count(args)
    budget_plan = resolve_budget_plan(args)
    max_overrun = budget_plan.max_overrun
    trace_console: TraceConsoleLevel = trace_console_from_args(args)
    strategy_selection = select_strategies(args)
    strategies = strategy_selection.strategies
    policy_jobs = strategy_selection.policy_jobs
    if strategy_selection.jobs_upgraded:
        print(
            f"{tag('policy-jobs', bold=False)} upgraded --jobs {args.jobs} -> {policy_jobs} "
            f"for {len(strategies)} policy-parallel strategies",
            flush=True,
        )

    budget_input = SwebenchBudgetAdapter().normalize(
        hard_cap_usd=budget_plan.constrained,
        soft_cap_usd=args.soft_budget,
        window="policy_batch",
        shared=True,
        budget_scale=args.budget_scale,
        source=budget_plan.source,
    )
    tasks = load_tasks_for_compare(args, tasks_n=tasks_n)

    # ── Model catalog: init before any cost estimation ────────────────────
    from budgetflow.model_tiers import init_catalog as _init_catalog, catalog_source_info as _catalog_source_info  # noqa: E402
    from budgetflow.tier_frontier import TierFrontier  # noqa: E402

    _frontier = TierFrontier.from_catalog()
    _budget_plan_data: dict | None = None
    planned_task_caps_by_strategy: dict[str, dict[str, float]] = {}
    budget_plan_path = Path(args.budget_plan) if getattr(args, "budget_plan", None) else None
    if budget_plan_path is not None and budget_plan_path.exists():
        import json as _json
        _budget_plan_data = _json.loads(budget_plan_path.read_text())
        raw_planned_caps = _budget_plan_data.get("planned_task_budget_by_strategy") or {}
        if isinstance(raw_planned_caps, dict):
            planned_task_caps_by_strategy = {
                str(strategy): {
                    str(task_id): float(cap)
                    for task_id, cap in caps.items()
                    if cap is not None and float(cap) > 0
                }
                for strategy, caps in raw_planned_caps.items()
                if isinstance(caps, dict)
            }
    calibrated_model_fit, calibrated_model_fit_source, calibrated_model_fit_confidence = calibrated_model_fit_from_budget_plan(
        budget_plan_path
    )

    if args.model_catalog:
        _init_catalog(Path(args.model_catalog))
        print(f"[catalog] loaded from {args.model_catalog}", flush=True)
        _frontier = TierFrontier.from_catalog()
    catalog_info = _catalog_source_info()

    catalog_issues = print_tier_catalog_preflight()

    runtime_root, _ = resolve_runtime_root()
    readiness = build_compare_readiness_report(
        args=args,
        tasks=tasks,
        strategies=strategies,
        policy_jobs=policy_jobs,
        value_context=value_context,
        catalog_issues=catalog_issues,
        runtime_root=runtime_root,
        budget_plan_path=budget_plan_path,
        per_task_cap=args.per_task_cap,
        runs_dir=RUNS_DIR,
    )
    print(format_readiness_report(readiness), flush=True)
    if args.paid_readiness_only:
        sys.exit(0 if readiness.ok else 2)
    if not readiness.ok:
        raise SystemExit("paid readiness preflight failed")

    # ── Provider signature check (AFTER dry-run/gate-only to avoid API calls) ──
    if not args.no_provider_signature_check:
        from budgetflow.provider_signature import check_required_signatures  # noqa: E402

        signature_results = check_required_signatures(_required_backends_for_strategies(strategies))
        for result in signature_results:
            state = "PASS" if result.ok else "FAIL"
            print(
                f"{tag('preflight', bold=False)} {state} backend={result.backend} "
                f"provider={result.provider} model={result.model} latency_ms={result.latency_ms} "
                f"status={result.status_code or '-'} error={result.error_type or '-'}",
                flush=True,
            )
        failed = [r for r in signature_results if not r.ok]
        if failed:
            raise SystemExit(
                "provider signature check failed: "
                + ", ".join(f"{r.backend}:{r.error_type or r.status_code}" for r in failed)
            )

    total_runs = len(tasks) * len(strategies)
    expected_run_keys = {
        (strategy.name, task.instance_id)
        for strategy in strategies
        for task in tasks
    }
    task_set_kind = _task_set_kind(task_set=args.task_set, ids=args.ids)
    out_stem, stem_mode, series_base, run_series = resolve_run_identity(
        RUNS_DIR,
        tasks_n=len(tasks),
        strategies_n=len(strategies),
        task_set=args.task_set,
        resume=args.resume,
        total_runs=total_runs,
        expected_keys=expected_run_keys,
        normalize_strategy=_normalize_strategy,
        explicit_stem=args.out_stem,
        explicit_series=args.run_series,
        repair=args.repair,
    )
    out_path, summary_path = _compare_paths(len(tasks), len(strategies), stem=out_stem)
    checkpoint_path = checkpoint_path_for(out_stem, RUNS_DIR)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    strategy_names = [s.name for s in strategies]
    completed_all = (
        _completed_keys(out_path, normalize_strategy=_normalize_strategy, skip_bad=args.skip_completed)
        if args.skip_completed else set()
    )
    completed = completed_all & expected_run_keys
    resume_scoreable_spend = (
        scoreable_spend_by_strategy(out_path, normalize_strategy=_normalize_strategy)
        if args.skip_completed else {}
    )
    if args.skip_completed and completed:
        print(f"{tag('resume', bold=False)} skip {len(completed)} completed (strategy,task) pairs", flush=True)
    ignored_completed = len(completed_all - expected_run_keys)
    if args.skip_completed and ignored_completed:
        print(
            f"{tag('resume', bold=False)} ignore {ignored_completed} completed pairs outside current task/strategy set",
            flush=True,
        )
    checkpoint = CompareCheckpointStore(
        checkpoint_path,
        stem=out_stem,
        total_runs=total_runs,
        completed_floor=len(completed),
    )
    # ── Frozen router plan for mechanism isolation ─────────────────────────
    frozen_plan = None
    if args.frozen_plan:
        frozen_plan = load_frozen_plan(args.frozen_plan)
        print(
            f"{tag('frozen_plan', bold=False)} loaded '{frozen_plan.name}' "
            f"with {len(frozen_plan.plan)} task entries",
            flush=True,
        )

    budget_modes_plan = build_batch_budget_modes(
        strategies=strategies,
        per_task_cap=args.per_task_cap,
        constrained_budget=budget_input["hard_cap_usd"],
        planned_task_caps_by_strategy=planned_task_caps_by_strategy,
    )
    batch_caps = budget_modes_plan.batch_caps
    budget_modes = budget_modes_plan.budget_modes
    validate_paper_mainline_budget_contract(
        strategies=strategies,
        batch_caps=batch_caps,
        budget_modes=budget_modes,
    )
    if args.resume:
        bp_task_ids = tuple(str(task_id) for task_id in ((_budget_plan_data or {}).get("task_ids") or ()))
        bp_strategy_names = tuple(str(name) for name in ((_budget_plan_data or {}).get("strategy_names") or ()))
        expected_contract = {
            "batch_budget_cap": budget_input["hard_cap_usd"],
            "budget_plan_hard_cap_usd": (_budget_plan_data or {}).get("hard_cap_usd"),
            "budget_plan_generation_mode": (_budget_plan_data or {}).get("generation_mode"),
            "budget_plan_task_ids": bp_task_ids,
            "budget_plan_strategy_names": bp_strategy_names,
            "catalog_revision": catalog_info.get("catalog_revision"),
            "catalog_path": catalog_info.get("catalog_path"),
            "catalog_content_hash": catalog_info.get("catalog_content_hash"),
            "value_profile": value_context.profile,
            "value_source_class": value_context.source_class,
            "value_matrix_artifact": value_context.matrix_path,
        }
        validate_resume_contract(out_path, expected_contract=expected_contract)

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    print_runtime_info(runtime_root, RUNS_DIR, out_stem, policy_jobs)
    print(
        f"{tag('run_id', bold=False)} {out_stem} "
        f"series={series_base} mode={stem_mode}"
        + (" (resume latest)" if stem_mode == "resume" else " (new run)"),
        flush=True,
    )
    from budgetflow.console_log import format_tier_pool_line  # noqa: E402

    print(
        f"{tag('compare', bold=False)} task_set={args.task_set} preset={args.preset} tasks={len(tasks)} "
        f"task_set_kind={task_set_kind} "
        f"strategies={len(strategies)} batches={len(strategies)} runs={total_runs} "
        f"budget={budget_input['hard_cap_usd']} budget_source={budget_input['source']} "
        f"pressure_init={budget_plan.pressure_init} pressure_max={budget_plan.pressure_max} "
        f"policy_jobs={policy_jobs} heartbeat={args.heartbeat}s hard_cap=settle_clamp",
        flush=True,
    )
    print(f"  pool: {format_tier_pool_line()}", flush=True)
    print(f"{dim('tasks=' + ','.join(t.instance_id for t in tasks))}", flush=True)
    print(f"{dim('task_order=' + ', '.join(_task_descriptor(t) for t in tasks))}", flush=True)
    print(f"{dim('strategies=' + ','.join(strategy_names))}", flush=True)
    if any(mode == "per_task_cap" for mode in budget_modes.values()):
        budget_mode = f"per_task_cap={args.per_task_cap}" + (f"+overrun={max_overrun}" if max_overrun else "")
    elif any(mode == "budgetflow_planned_task_budget" for mode in budget_modes.values()):
        planned_names = [name for name, mode in budget_modes.items() if mode == "budgetflow_planned_task_budget"]
        budget_mode = "shared_batch_hard_budget + budgetflow_planned_task_budget(" + ",".join(planned_names) + ")"
    else:
        budget_mode = "shared_batch_hard_budget" + (
            f" soft_budget={args.soft_budget}+overrun={max_overrun}" if args.soft_budget is not None else ""
        )
    print(
        f"{dim('mode=' + budget_mode + '; tasks serial within policy; policies parallel with --jobs')}",
        flush=True,
    )
    if args.w_profile:
        print(f"{dim('w_i_profile=' + args.w_profile)}", flush=True)
    if calibrated_model_fit:
        print(
            f"{dim('model_fit=' + calibrated_model_fit_source + ' confidence=' + calibrated_model_fit_confidence + ' ' + str(calibrated_model_fit))}",
            flush=True,
        )
    print(f"{dim('trace_console=' + trace_console + '; heartbeat every ' + str(args.heartbeat) + 's')}", flush=True)
    if args.max_tasks_per_strategy is not None:
        print(
            f"{dim('stage_cap=max_tasks_per_strategy=' + str(args.max_tasks_per_strategy) + '/' + str(len(tasks)))}",
            flush=True,
        )
    print(f"{dim('run_id=' + out_stem)}", flush=True)
    print(f"{dim('out=' + str(out_path))}", flush=True)
    print(f"{dim('checkpoint=' + str(checkpoint_path))}", flush=True)
    print(f"{dim('trace= data/runs/trace_<id>_<strategy>/steps.jsonl')}", flush=True)
    print(f"{dim('FORCE_COLOR=1 if piping to tee/nohup for ANSI colors')}", flush=True)

    # ── PolicyMemory ────────────────────────────────────────────────────
    policy_ctx = load_policy_memory_context(
        runs_dir=RUNS_DIR,
        repo_root=REPO_ROOT,
        explicit_path=args.policy_memory,
        resume=args.resume,
        resume_path=out_path,
        disable=args.disable_policy_memory,
        regret_threshold=args.regret_threshold,
        exclude=out_path,
    )
    policy_memory = policy_ctx.memory
    if policy_ctx.enabled and policy_memory is not None and policy_ctx.source is not None:
        source_display = ",".join(str(path) for path in policy_ctx.sources) or str(policy_ctx.source)
        print(f"{tag('policy_memory', bold=True)} loaded from {source_display} "
              f"source={policy_ctx.source_kind} "
              f"records={policy_memory._record_count} "
              f"effective_weight={policy_memory._effective_record_weight:.2f} "
              f"repos={len(policy_memory._repo_priors)} "
              f"tasks={len(policy_memory._task_priors)} "
              f"threshold={policy_memory.regret_threshold}")
    else:
        print(f"{tag('policy_memory', bold=False)} disabled — {policy_ctx.reason or 'no usable run JSONL source found'}")

    adaptive_registry = AdaptiveRoutingRegistry(learn_policy_inputs=policy_ctx.learn_policy_inputs)
    if args.append and out_path.is_file():
        adaptive_registry.rebuild_from_jsonl(out_path)

    header_lines = [
        f"compare_{len(tasks)}x{len(strategies)} task_set={args.task_set} preset={args.preset} "
        f"task_set_kind={task_set_kind} tasks={len(tasks)} strategies={strategy_names}",
        f"budget_mode={budget_mode} "
        f"soft_budget={args.soft_budget} max_overrun={max_overrun} "
        f"budget={budget_input['hard_cap_usd']} budget_source={budget_input['source']} "
        f"w_i_profile={args.w_profile or active_w_i_profile_name()} "
        f"pressure_init={budget_plan.pressure_init} pressure_max={budget_plan.pressure_max} "
        f"policy_jobs={policy_jobs} hard_cap=settle_clamp",
        f"tasks={[t.instance_id for t in tasks]}",
        f"task_order={[_task_descriptor(t) for t in tasks]}",
        "adaptive_routing=always_on_for_budgetflow_segment",
        "",
    ]
    adapt_summary = adaptive_registry.summary_lines()
    header_lines.extend(adapt_summary)
    if adapt_summary:
        header_lines.append("")
    if args.append and out_path.is_file():
        state = _rebuild_state_from_jsonl(
            out_path,
            header_lines,
            normalize_strategy=_normalize_strategy,
            enrich_value=enrich_record_final,
        )
        print(f"{tag('resume', bold=False)} rebuilt state from jsonl runs={state.runs_done}", flush=True)
    else:
        state = CompareRunState.empty(header_lines)
    started = time.time()
    io_lock = threading.Lock()
    print_lock = threading.Lock() if policy_jobs > 1 else None
    heartbeat_path = RUNS_DIR / f"{run_series}.heartbeat.json"
    heartbeat_writer = HeartbeatWriter(heartbeat_path, run_series=run_series, total_expected=total_runs)
    global_progress = GlobalRunProgress(total_runs)
    scoreboard = StrategyScoreboard(strategy_names)
    if completed:
        global_progress.seed_done(len(completed))
    if args.append:
        heartbeat_writer.pulse(rows_done=state.runs_done)
    if args.append and state.resolved_by_strategy:
        scoreboard.seed_from_resolved(state.resolved_by_strategy, state.score_status_by_strategy)

    _write_summary_snapshot(
        summary_path,
        state=state,
        strategy_names=strategy_names,
        batch_caps=batch_caps,
        budget_modes=budget_modes,
        started=started,
        out_path=out_path,
        total_runs=total_runs,
        tasks_per_strategy=len(tasks),
        global_line=global_progress.format_global(scoreboard),
        value_profile=value_context.profile,
    )

    run_guards: CompareRunGuards | None = None if args.no_run_guards else CompareRunGuards()
    set_active_guard(run_guards)

    def _run_one_batch(cfg: CompareStrategy) -> tuple[CompareStrategy, list[dict], float, float]:
        if run_guards is not None and run_guards.is_aborted():
            print(
                f"{tag('guard', bold=False)} skip strategy={cfg.name} batch (global halt: {run_guards.abort_reason()})",
                flush=True,
            )
            batch_cap = _batch_budget_cap(cfg, budget_input["hard_cap_usd"])
            return cfg, [], resume_scoreable_spend.get(cfg.name, 0.0) if args.resume else 0.0, batch_cap
        batch_cap = _batch_budget_cap(cfg, budget_input["hard_cap_usd"])
        batch_tasks = select_stage_batch_tasks(
            tasks,
            strategy_name=cfg.name,
            completed=completed,
            max_tasks_per_strategy=args.max_tasks_per_strategy,
        )
        if not batch_tasks:
            if args.max_tasks_per_strategy is not None:
                print(
                    f"{tag('skip', bold=False)} strategy={cfg.name} "
                    f"stage target {args.max_tasks_per_strategy}/{len(tasks)} already reached",
                    flush=True,
                )
            else:
                print(f"{tag('skip', bold=False)} strategy={cfg.name} all tasks already done", flush=True)
            return cfg, [], 0.0, batch_cap
        if args.max_tasks_per_strategy is not None:
            print(
                f"{tag('stage', bold=False)} strategy={cfg.name} running {len(batch_tasks)} "
                f"remaining task(s) toward {args.max_tasks_per_strategy}/{len(tasks)}",
                flush=True,
            )
        initial_spent = resume_scoreable_spend.get(cfg.name, 0.0) if args.resume else 0.0

        def _on_task(record: dict) -> None:
            _persist_task_record(
                state,
                record,
                handle=handle,
                io_lock=io_lock,
                total_runs=total_runs,
                tasks_per_strategy=len(tasks),
                global_progress=global_progress,
                scoreboard=scoreboard,
                summary_path=summary_path,
                strategy_names=strategy_names,
                batch_caps=batch_caps,
                budget_modes=budget_modes,
                started=started,
                out_path=out_path,
                value_profile=value_context.profile,
                enrich_value=enrich_record_final,
            )
            heartbeat_writer.pulse(
                rows_done=state.runs_done,
                active_strategy=str(record.get("strategy", "")),
                active_instance=str(record.get("instance_id", "")),
                active_elapsed_s=float(record.get("elapsed_s", 0)),
                last_completed=str(record.get("instance_id", "")),
            )

        _eff_budget_mode = budget_modes[cfg.name] if budget_modes and cfg.name in budget_modes else None
        records, batch_spent = run_strategy_batch(
            cfg,
            batch_tasks,
            batch_budget_cap=batch_cap,
            value_context=value_context,
            per_task_cap=args.per_task_cap if args.per_task_cap and args.per_task_cap > 0 else None,
            planned_task_caps=planned_task_caps_by_strategy.get(cfg.name),
            soft_budget=args.soft_budget,
            max_overrun=max_overrun,
            step_limit=args.step_limit,
            trace_console=trace_console,
            heartbeat=args.heartbeat,
            global_progress=global_progress,
            scoreboard=scoreboard,
            print_lock=print_lock,
            budget_pressure=budget_plan.pressure_init,
            pressure_max=budget_plan.pressure_max,
            initial_spent=initial_spent,
            checkpoint=checkpoint,
            on_task_complete=_on_task,
            run_guards=run_guards,
            adaptive_registry=adaptive_registry,
            enable_turn_trace=args.trace_turns,
            trace_max_turns=args.trace_max_turns,
            trace_truncate_chars=args.trace_truncate_chars,
            budget_input=budget_input,
            run_series=run_series,
            heartbeat_writer=heartbeat_writer,
            task_set=args.task_set,
            task_set_kind=task_set_kind,
            frozen_plan=frozen_plan,
            budget_mode=_eff_budget_mode,
            calibrated_model_fit=calibrated_model_fit,
            calibrated_model_fit_source=calibrated_model_fit_source,
            calibrated_model_fit_confidence=calibrated_model_fit_confidence,
        )
        return cfg, records, batch_spent, batch_cap

    file_mode = "a" if args.append else "w"
    try:
        with out_path.open(file_mode) as handle:
            if policy_jobs <= 1:
                for cfg in strategies:
                    if run_guards is not None and run_guards.is_aborted():
                        break
                    cfg, batch_records, batch_spent, batch_cap = _run_one_batch(cfg)
                    _ingest_batch_footer(
                        state,
                        cfg,
                        batch_records,
                        batch_spent,
                        batch_cap,
                        strategy_names=strategy_names,
                        batch_caps=batch_caps,
                        budget_modes=budget_modes,
                        summary_path=summary_path,
                        started=started,
                        out_path=out_path,
                        total_runs=total_runs,
                        tasks_per_strategy=len(tasks),
                        io_lock=io_lock,
                        global_progress=global_progress,
                        value_profile=value_context.profile,
                    )
            else:
                with ThreadPoolExecutor(max_workers=min(policy_jobs, len(strategies))) as pool:
                    futures = {pool.submit(_run_one_batch, cfg): cfg for cfg in strategies}
                    for future in as_completed(futures):
                        cfg, batch_records, batch_spent, batch_cap = future.result()
                        if run_guards is not None and run_guards.is_aborted():
                            for pending in futures:
                                pending.cancel()
                            break
                        _ingest_batch_footer(
                            state,
                            cfg,
                            batch_records,
                            batch_spent,
                            batch_cap,
                            strategy_names=strategy_names,
                            batch_caps=batch_caps,
                            budget_modes=budget_modes,
                            summary_path=summary_path,
                            started=started,
                            out_path=out_path,
                            total_runs=total_runs,
                            tasks_per_strategy=len(tasks),
                            io_lock=io_lock,
                            global_progress=global_progress,
                            value_profile=value_context.profile,
                        )
    finally:
        set_active_guard(None)
        release_run_identity(out_stem, RUNS_DIR)

    if run_guards is not None and run_guards.is_aborted():
        print(f"\n{tag('guard', bold=False)} run stopped early: {run_guards.abort_reason()}", flush=True)

    _write_summary_snapshot(
        summary_path,
        state=state,
        strategy_names=strategy_names,
        batch_caps=batch_caps,
        budget_modes=budget_modes,
        started=started,
        out_path=out_path,
        total_runs=total_runs,
        tasks_per_strategy=len(tasks),
        global_line=global_progress.format_global(scoreboard),
        value_profile=value_context.profile,
    )

    heartbeat_writer.mark_done()
    print(
        f"\n{tag('final', bold=False)}\n{global_progress.format_banner(scoreboard)}\n"
        f"elapsed={time.time() - started:.1f}s",
        flush=True,
    )
    for line in _format_strategy_totals(
        strategy_names=strategy_names,
        resolved_by_strategy=state.resolved_by_strategy,
        score_status_by_strategy=state.score_status_by_strategy,
        task_cost_by_strategy=state.task_cost_by_strategy,
        batch_spent_by_strategy=state.batch_spent_by_strategy,
        turns_by_strategy=state.turns_by_strategy,
        tier_mix_by_strategy=state.tier_mix_by_strategy,
        failure_by_strategy=state.failure_by_strategy,
        batch_caps=batch_caps,
        budget_modes=budget_modes,
    ):
        print(f"  {line}", flush=True)
    print(f"jsonl={out_path}")
    print(f"summary={summary_path}")
    if out_path.is_file():
        try:
            crosscheck = build_crosscheck_artifacts(
                out_path,
                out_dir=out_path.parent,
                run_id=f"{out_stem}-official-crosscheck",
            )
            state.summary_lines.append("")
            state.summary_lines.append("=== OFFICIAL HARNESS CROSS-CHECK ARTIFACT ===")
            state.summary_lines.append(
                "dry_run_artifact_only "
                f"selected={crosscheck['selected_rows']} "
                f"predictions={crosscheck['predictions_path']} "
                f"manifest={crosscheck['manifest_path']} "
                f"command={crosscheck['command_path']}"
            )
            if crosscheck.get("preflight_warnings"):
                state.summary_lines.append(
                    "preflight_warnings="
                    + ",".join(str(warning) for warning in crosscheck["preflight_warnings"])
                )
            _write_summary_snapshot(
                summary_path,
                state=state,
                strategy_names=strategy_names,
                batch_caps=batch_caps,
                budget_modes=budget_modes,
                started=started,
                out_path=out_path,
                total_runs=total_runs,
                tasks_per_strategy=len(tasks),
                global_line=global_progress.format_global(scoreboard),
                value_profile=value_context.profile,
            )
            print(f"official_crosscheck_manifest={crosscheck['manifest_path']}")
        except Exception as exc:  # pragma: no cover - best-effort artifact, not scoring
            print(f"{tag('official', bold=False)} cross-check artifact warning: {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    main()
