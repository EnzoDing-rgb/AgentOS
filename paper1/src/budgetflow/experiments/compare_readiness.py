"""Pre-provider readiness checks for BudgetFlow compare runs.

This module owns the launch-time contract for paid diagnostics. It does not
judge run outcomes; it only blocks runs whose setup would be hard to interpret.
"""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
import importlib.util
import math
from pathlib import Path

from budgetflow.experiments.compare_config import CompareStrategy, paper_mainline_strategy_names
from budgetflow.experiments.budget_binding import ALLOWED_GENERATION_MODES, STAGE_PREFIX_PRESSURE_MODE
from budgetflow.experiments.compare_setup import PLANNED_TASK_BUDGET_MODE, PLANNED_TASK_BUDGET_ROUTINGS
from budgetflow.defaults import PAID_MAINLINE_STEP_LIMIT
from budgetflow.failure_classification import build_score_status, build_verdict
from budgetflow.frozen_router import load_frozen_plan
from budgetflow.harness_contamination import (
    find_runtime_worktree_python_contamination,
    format_runtime_worktree_contamination,
)
from budgetflow.model_tiers import (
    DEFAULT_CATALOG_PATH,
    MODEL_CATALOG,
    catalog_path,
    catalog_revision,
    catalog_source_info,
)
from budgetflow.run_series import retired_series_reason
from budgetflow.value_efficiency import ValueEfficiencyContext

FROZEN_PLAN_ROUTINGS = frozenset({
    "enterprise_router",
    "budgetflow_same_router",
    "routellm_learned_router",
})


@dataclass(frozen=True)
class ReadinessReport:
    blocking: tuple[str, ...]
    warnings: tuple[str, ...]
    facts: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.blocking


_REPO_HARNESS_REQUIRED_MODULES: dict[str, tuple[str, ...]] = {
    "mwaskom/seaborn": ("matplotlib",),
    "sphinx-doc/sphinx": ("requests",),
}


def _missing_selected_harness_dependencies(tasks: list) -> dict[str, tuple[str, ...]]:
    missing: dict[str, tuple[str, ...]] = {}
    selected_repos = sorted({
        str(getattr(task, "repo", "") or "")
        for task in tasks
        if str(getattr(task, "repo", "") or "")
    })
    for repo in selected_repos:
        required = _REPO_HARNESS_REQUIRED_MODULES.get(repo, ())
        repo_missing = tuple(
            module for module in required if importlib.util.find_spec(module) is None
        )
        if repo_missing:
            missing[repo] = repo_missing
    return missing


def _find_existing_jsonl(run_series: str | None, runs_dir: Path | None) -> Path | None:
    """Return the JSONL path for *run_series* if it already exists on disk."""
    if not run_series or runs_dir is None:
        return None
    candidate = Path(runs_dir) / f"{run_series}-0.jsonl"
    if candidate.is_file():
        return candidate
    return None


def _compute_protocol_health(jsonl_path: Path) -> dict:
    """Compute protocol health from existing JSONL using current classifiers."""
    import json as _json

    total_rows = 0
    protocol_abort_rows = 0
    failed_protocol_retry_rows = 0
    no_tool_call_rows = 0

    with jsonl_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = _json.loads(line)
            except _json.JSONDecodeError:
                continue
            total_rows += 1

            verdict = build_verdict(row)
            score = build_score_status(row)
            score_status = str(score.get("score_status") or "")
            failure_owner = str(verdict.get("failure_owner") or "")
            abort_owner = str(score.get("abort_owner") or "")
            exit_owner = str(score.get("exit_owner") or "")
            exit_reason = str(row.get("exit_reason") or "")
            if (
                score_status == "abort"
                and (
                    failure_owner == "protocol"
                    or abort_owner == "protocol"
                    or exit_owner in {"protocol", "parser_protocol"}
                    or exit_reason.startswith("format_error_")
                )
            ):
                protocol_abort_rows += 1

            retry_used = bool(row.get("protocol_retry_used"))
            retry_success = bool(row.get("protocol_retry_success"))
            retry_reason = str(row.get("protocol_retry_reason") or "")
            if retry_used and not retry_success:
                failed_protocol_retry_rows += 1
            if retry_reason in {"found_0_actions", "no_tool_calls"}:
                no_tool_call_rows += 1

    if total_rows == 0:
        return {
            "total_rows": 0,
            "protocol_abort_rate": 0.0,
            "failed_protocol_retry_rate": 0.0,
            "no_tool_call_rate": 0.0,
        }

    return {
        "total_rows": total_rows,
        "protocol_abort_rate": protocol_abort_rows / total_rows,
        "failed_protocol_retry_rate": failed_protocol_retry_rows / total_rows,
        "no_tool_call_rate": no_tool_call_rows / total_rows,
    }


def build_compare_readiness_report(
    *,
    args: Namespace,
    tasks: list,
    strategies: tuple[CompareStrategy, ...],
    policy_jobs: int,
    value_context: ValueEfficiencyContext,
    catalog_issues: list[str],
    runtime_root: Path,
    budget_plan_path: Path | None = None,
    per_task_cap: float | None = None,
    runs_dir: Path | None = None,
) -> ReadinessReport:
    blocking: list[str] = []
    warnings: list[str] = []
    facts: list[str] = []

    task_ids = [str(task.instance_id) for task in tasks]
    strategy_names = [strategy.name for strategy in strategies]
    use_fixed_per_task_cap = per_task_cap is not None and per_task_cap > 0

    facts.append(f"tasks={len(task_ids)}")
    facts.append(f"strategies={len(strategy_names)}")
    facts.append(f"policy_jobs={policy_jobs}")
    step_limit = int(getattr(args, "step_limit", PAID_MAINLINE_STEP_LIMIT) or 0)
    facts.append(f"step_limit={step_limit}")
    facts.append(f"value_profile={value_context.profile}")
    facts.append(f"value_source_class={value_context.source_class}")
    facts.append(f"value_evidence={value_context.evidence_role}")
    facts.append(f"value_confidence={value_context.confidence}")
    facts.append(f"value_primary_claim1={str(value_context.is_primary_value_evidence).lower()}")
    facts.append(f"value_matrix={value_context.matrix_path or 'equal_sanity'}")
    facts.append(f"runtime_root={runtime_root}")
    site_contamination = find_runtime_worktree_python_contamination(runtime_root)
    if site_contamination:
        blocking.append(
            "global Python environment contains runtime worktree paths; "
            "remove stale .pth/sys.path entries before paid runs: "
            f"{format_runtime_worktree_contamination(site_contamination)}"
        )
    mainline_strategy_names = list(paper_mainline_strategy_names())
    is_paper_mainline = strategy_names == mainline_strategy_names
    facts.append(f"paper_mainline={str(is_paper_mainline).lower()}")
    frozen_plan_arg = getattr(args, "frozen_plan", None)
    frozen_plan = None
    uses_frozen_plan_routing = any(
        strategy.routing in FROZEN_PLAN_ROUTINGS
        for strategy in strategies
    )
    if use_fixed_per_task_cap:
        facts.append("budget_mode=per_task_cap")
    else:
        facts.append("budget_mode=shared_batch_hard_budget")

    if not task_ids:
        blocking.append("no tasks selected")
    run_series = getattr(args, "run_series", None)
    out_stem = getattr(args, "out_stem", None)
    if run_series:
        retired_reason = retired_series_reason(series=str(run_series), explicit_stem=out_stem)
        if retired_reason:
            blocking.append(
                f"retired run series cannot be used for paid readiness: {retired_reason}"
            )
    missing_test_patch = [task_id for task_id, task in zip(task_ids, tasks) if not getattr(task, "test_patch", None)]
    missing_fail_to_pass = [task_id for task_id, task in zip(task_ids, tasks) if not getattr(task, "fail_to_pass", ())]
    if missing_test_patch:
        preview = ", ".join(missing_test_patch[:8])
        suffix = "" if len(missing_test_patch) <= 8 else f", ... +{len(missing_test_patch) - 8} more"
        blocking.append(
            f"{len(missing_test_patch)} selected tasks lack test_patch; evaluation cannot verify fail-before/fail-after: "
            f"{preview}{suffix}"
        )
    if missing_fail_to_pass:
        preview = ", ".join(missing_fail_to_pass[:8])
        suffix = "" if len(missing_fail_to_pass) <= 8 else f", ... +{len(missing_fail_to_pass) - 8} more"
        blocking.append(
            f"{len(missing_fail_to_pass)} selected tasks lack fail_to_pass tests; verified value cannot be trusted: "
            f"{preview}{suffix}"
        )
    missing_harness_deps = _missing_selected_harness_dependencies(tasks)
    for repo, modules in missing_harness_deps.items():
        blocking.append(
            f"selected repo {repo} has missing harness dependencies: "
            f"{', '.join(modules)}; install/localize dependencies or remove these tasks before paid runs"
        )
    if not strategy_names:
        blocking.append("no strategies selected")
    if step_limit <= 0:
        blocking.append("--step-limit must be positive")
    elif is_paper_mainline and step_limit > PAID_MAINLINE_STEP_LIMIT:
        blocking.append(
            f"paper mainline step_limit={step_limit} exceeds "
            f"paid safety cap {PAID_MAINLINE_STEP_LIMIT}; use a non-mainline diagnostic "
            "strategy set if a longer exploratory run is required"
        )
    if len(strategy_names) > 1 and policy_jobs < len(strategy_names):
        blocking.append(
            f"policy_jobs={policy_jobs} is below strategy_count={len(strategy_names)}; "
            "policies must run in parallel and tasks serial within each policy"
        )
    if catalog_issues:
        blocking.extend(f"tier catalog: {issue}" for issue in catalog_issues)
    active_protocols = {cfg.backend: cfg.protocol for cfg in MODEL_CATALOG.configs}
    facts.append(
        "catalog_protocols="
        + ",".join(f"{backend}:{protocol}" for backend, protocol in sorted(active_protocols.items()))
    )
    if is_paper_mainline:
        non_tool_call = {
            backend: protocol
            for backend, protocol in active_protocols.items()
            if protocol != "tool_call"
        }
        if non_tool_call:
            blocking.append(
                "paper mainline requires native tool_call action protocol for every tier; "
                f"found {non_tool_call}"
            )
    active_catalog_path = catalog_path()
    active_catalog_revision = catalog_revision()
    uses_default_catalog = (
        active_catalog_path is not None
        and Path(active_catalog_path).resolve() == Path(DEFAULT_CATALOG_PATH).resolve()
    )
    diagnostic_catalog = bool(active_catalog_revision and not uses_default_catalog)
    if diagnostic_catalog:
        facts.append(f"catalog_role=diagnostic revision={active_catalog_revision}")
        if not getattr(args, "diagnostic_catalog", False):
            blocking.append(
                "non-default model catalog requires --diagnostic-catalog; "
                "diagnostic cost catalogs must be explicit in paid-run evidence"
            )
    else:
        facts.append(f"catalog_role=default revision={active_catalog_revision}")
    if getattr(args, "no_provider_signature_check", False):
        blocking.append(
            "--no-provider-signature-check is not allowed for paid-run readiness; "
            "provider/model access must be verified before spending budget"
        )
    if is_paper_mainline and budget_plan_path is None:
        blocking.append(
            "paper mainline paid runs require --budget-plan generated by the Budget Regime Compiler"
        )
    if is_paper_mainline and not value_context.is_primary_value_evidence:
        blocking.append(
            "paper mainline paid runs require primary value evidence: use "
            "--value-source-kind pre_registered_manual with a covered value matrix"
        )
    if budget_plan_path is not None and use_fixed_per_task_cap:
        blocking.append(
            "--budget-plan uses the Budget Regime Compiler shared-batch contract; "
            "--per-task-cap changes budget semantics. Do not combine them."
        )

    if value_context.profile != "equal":
        if not value_context.matrix_path:
            blocking.append(f"value_profile={value_context.profile} requires --value-matrix")
        missing = value_context.missing_task_values(task_ids)
        if missing:
            preview = ", ".join(missing[:8])
            suffix = "" if len(missing) <= 8 else f", ... +{len(missing) - 8} more"
            blocking.append(
                f"value matrix is missing {len(missing)} selected task values: {preview}{suffix}"
            )
    needs_task_values = any(
        strategy.routing in {"segment_value_aware", "value_aware_task_level"}
        for strategy in strategies
    )
    needs_frozen_plan = any(
        strategy.routing in FROZEN_PLAN_ROUTINGS
        for strategy in strategies
    )
    if needs_frozen_plan and not frozen_plan_arg:
        frozen_names = [strategy.name for strategy in strategies if strategy.routing in FROZEN_PLAN_ROUTINGS]
        blocking.append(
            f"frozen-plan strategies require --frozen-plan: {frozen_names}"
        )
    elif needs_frozen_plan and frozen_plan_arg:
        try:
            frozen_plan = load_frozen_plan(frozen_plan_arg)
        except (OSError, ValueError, TypeError) as exc:
            blocking.append(f"cannot load frozen router plan: {exc}")
        else:
            facts.append(f"frozen_plan={frozen_plan.name}")
            facts.append(f"frozen_plan_entries={len(frozen_plan.plan)}")
            requested_budget = float(getattr(args, "budget", 0.0) or 0.0)
            budget_is_from_plan = bool(requested_budget == 0.0 and budget_plan_path is not None)
            if budget_is_from_plan:
                facts.append("budget_source=budget_plan")
            elif requested_budget == 0.0:
                facts.append("budget_source=unset")
                if is_paper_mainline:
                    blocking.append(
                        "paper mainline paid runs must use --budget-plan; "
                        "frozen router plans provide routing priors, not budget caps"
                    )
            else:
                facts.append(f"budget_source=cli")
                facts.append(f"budget={requested_budget:.4f}")
            missing_plan = [task_id for task_id in task_ids if frozen_plan.lookup(task_id) is None]
            if missing_plan:
                preview = ", ".join(missing_plan[:8])
                suffix = "" if len(missing_plan) <= 8 else f", ... +{len(missing_plan) - 8} more"
                blocking.append(
                    f"frozen router plan is missing {len(missing_plan)} selected tasks: "
                    f"{preview}{suffix}"
                )
    if value_context.profile == "equal":
        warnings.append(
            "running non-trivial experiment with equal task values; "
            "Total Resolved Value reduces to Resolved Count and is a diagnostic "
            "view, not primary value evidence. Use a pre-registered manual "
            "value matrix for Claim 1 value claims."
        )
    if needs_task_values and value_context.profile == "equal":
        warnings.append(
            "equal task values make value-aware strategies a mechanism diagnostic, not primary value evidence"
        )
    if needs_task_values and not value_context.is_primary_value_evidence:
        warnings.append(
            f"value_source_kind={value_context.source_class} is not primary Claim 1 value evidence; "
            "use --value-source-kind pre_registered_manual with a frozen matrix for main Total Resolved Value claims"
        )

    if args.task_set != "medium" and not args.ids and len(task_ids) <= 3:
        warnings.append("small familiar task set; diagnostic only, weak anti-overfitting evidence")
    if not args.trace_turns:
        warnings.append("turn traces disabled; strongest-model productivity/source breakdown will be weak")

    # ── Budget binding plan validation ───────────────────────────────────
    if budget_plan_path is not None:
        try:
            import json as _json
            with budget_plan_path.open() as _fh:
                bp = _json.load(_fh)
        except (OSError, ValueError, TypeError) as exc:
            blocking.append(f"cannot load budget plan {budget_plan_path}: {exc}")
        else:
            facts.append(f"budget_plan={budget_plan_path}")
            facts.append(f"budget_plan_source={bp.get('source', 'unknown')}")
            facts.append(f"budget_plan_generation_mode={bp.get('generation_mode', 'unknown')}")
            facts.append(f"budget_plan_decision={bp.get('decision', 'UNKNOWN')}")
            bp_hard_cap = float(bp.get("hard_cap_usd", 0.0) or 0.0)
            facts.append(f"budget_plan_hard_cap={bp_hard_cap:.4f}")
            bp_reasons = bp.get("reasons", [])
            for reason in bp_reasons:
                facts.append(f"budget_plan_reason: {reason}")
            bp_decision = bp.get("decision", "")
            bp_generation_mode = str(bp.get("generation_mode", "") or "")
            if not bp_generation_mode:
                blocking.append(
                    "budget plan is missing generation_mode; regenerate it with the Budget Regime Compiler"
                )
            elif bp_generation_mode not in ALLOWED_GENERATION_MODES:
                blocking.append(
                    "budget plan generation_mode must be one of "
                    f"{sorted(ALLOWED_GENERATION_MODES)}; regenerate it with the Budget Regime Compiler"
                )
            elif bp_generation_mode == STAGE_PREFIX_PRESSURE_MODE:
                spec = bp.get("budget_pressure_spec")
                if not isinstance(spec, dict):
                    blocking.append(
                        "stage_prefix_pressure budget plan is missing budget_pressure_spec; "
                        "regenerate it with the Budget Regime Compiler"
                    )
                else:
                    prefix_count = int(spec.get("stage_prefix_count") or 0)
                    target_fraction = float(spec.get("stage_target_budget_fraction") or 0.0)
                    reference_strategy = str(spec.get("stage_reference_strategy") or "")
                    if prefix_count <= 0:
                        blocking.append(
                            "stage_prefix_pressure budget plan has invalid stage_prefix_count; "
                            "regenerate it with the Budget Regime Compiler"
                        )
                    if prefix_count > len(task_ids):
                        blocking.append(
                            f"stage_prefix_pressure budget plan stage_prefix_count={prefix_count} "
                            f"exceeds selected task count={len(task_ids)}; the prefix must be a "
                            "leading subset of the selected task order"
                        )
                    max_tasks_per_strategy = getattr(args, "max_tasks_per_strategy", None)
                    if max_tasks_per_strategy is not None and max_tasks_per_strategy > 0:
                        staged_run = min(int(max_tasks_per_strategy), len(task_ids))
                        if prefix_count > staged_run:
                            blocking.append(
                                f"stage_prefix_pressure budget plan stage_prefix_count={prefix_count} "
                                f"exceeds --max-tasks-per-strategy={max_tasks_per_strategy} "
                                f"(staged run={staged_run}); do not run a partial prefix with "
                                "a cap compiled from tasks that will not execute in this invocation"
                            )
                    if not (0.0 < target_fraction <= 1.0):
                        blocking.append(
                            "stage_prefix_pressure budget plan has invalid "
                            "stage_target_budget_fraction; regenerate it with the Budget Regime Compiler"
                        )
                    if not reference_strategy:
                        blocking.append(
                            "stage_prefix_pressure budget plan is missing stage_reference_strategy; "
                            "regenerate it with the Budget Regime Compiler"
                        )
            if bp_decision == "BLOCK":
                blocking.append(
                    f"budget plan decision is BLOCK: {'; '.join(bp_reasons)}"
                )
            requested_budget = float(getattr(args, "budget", 0.0) or 0.0)
            if requested_budget > 0 and abs(requested_budget - bp_hard_cap) > 0.0001:
                blocking.append(
                    f"--budget={requested_budget:.4f} does not match "
                    f"budget_plan hard_cap={bp_hard_cap:.4f}; "
                    f"use the budget plan value or omit --budget"
                )
            bp_task_ids = bp.get("task_ids")
            if isinstance(bp_task_ids, list) and bp_task_ids:
                bp_task_list = [str(task_id) for task_id in bp_task_ids]
                facts.append(f"budget_plan_task_ids={len(bp_task_list)}")
                selected_set = set(task_ids)
                budget_set = set(bp_task_list)
                if budget_set != selected_set:
                    missing_budget_tasks = [task_id for task_id in task_ids if task_id not in budget_set]
                    extra_budget_tasks = [task_id for task_id in bp_task_list if task_id not in selected_set]
                    detail_parts: list[str] = []
                    if missing_budget_tasks:
                        preview = ", ".join(missing_budget_tasks[:8])
                        suffix = "" if len(missing_budget_tasks) <= 8 else f", ... +{len(missing_budget_tasks) - 8} more"
                        detail_parts.append(f"missing selected tasks: {preview}{suffix}")
                    if extra_budget_tasks:
                        preview = ", ".join(extra_budget_tasks[:8])
                        suffix = "" if len(extra_budget_tasks) <= 8 else f", ... +{len(extra_budget_tasks) - 8} more"
                        detail_parts.append(f"extra budget-plan tasks: {preview}{suffix}")
                    if not detail_parts:
                        detail_parts.append("same task set but different order")
                    blocking.append(
                        "budget plan task_ids must exactly match selected task set; "
                        + "; ".join(detail_parts)
                    )
                elif bp_task_list != task_ids:
                    blocking.append(
                        "budget plan task_ids order must exactly match selected task order; "
                        "planned-task effective caps are order-sensitive under the shared hard budget. "
                        f"budget_plan_order={bp_task_list[:8]} "
                        f"selected_order={task_ids[:8]}"
                    )
                bp_generation_mode = str(bp.get("generation_mode", "") or "")
            bp_strategy_names = bp.get("strategy_names")
            if isinstance(bp_strategy_names, list) and bp_strategy_names:
                expected_strategies = [str(name) for name in bp_strategy_names]
                facts.append(f"budget_plan_strategies={len(expected_strategies)}")
                if strategy_names != expected_strategies:
                    blocking.append(
                        "selected strategies do not match budget plan strategy set/order: "
                        f"selected={strategy_names}; budget_plan={expected_strategies}"
                    )
            else:
                mainline = list(paper_mainline_strategy_names())
                if strategy_names == mainline:
                    blocking.append(
                        "budget plan is missing strategy_names; regenerate it with the Budget Regime Compiler "
                        "before a paper-mainline paid run"
                    )

            planned_task_budget_names = [
                strategy.name for strategy in strategies if strategy.routing in PLANNED_TASK_BUDGET_ROUTINGS
            ]
            planned_caps = bp.get("planned_task_budget_by_strategy")
            if planned_task_budget_names:
                planned_policy = bp.get("planned_task_budget_policy")
                planned_mode = ""
                if isinstance(planned_policy, dict):
                    planned_mode = str(planned_policy.get("mode") or "")
                if planned_mode and planned_mode != PLANNED_TASK_BUDGET_MODE:
                    blocking.append(
                        "budget plan planned_task_budget_policy.mode="
                        f"{planned_mode!r} does not match runtime mode "
                        f"{PLANNED_TASK_BUDGET_MODE!r}; regenerate it with the current "
                        "Budget Regime Compiler"
                    )
                if not isinstance(planned_caps, dict) or not planned_caps:
                    blocking.append(
                        "budget plan is missing planned_task_budget_by_strategy for "
                        f"planned-task-budget policies {planned_task_budget_names}; "
                        "regenerate it with the current Budget Regime Compiler"
                    )
                else:
                    for strategy_name in planned_task_budget_names:
                        strategy_caps = planned_caps.get(strategy_name)
                        if not isinstance(strategy_caps, dict) or not strategy_caps:
                            blocking.append(
                                f"budget plan is missing planned task budgets for {strategy_name}; "
                                "regenerate it with the current Budget Regime Compiler"
                            )
                            continue
                        missing_caps = [task_id for task_id in task_ids if task_id not in strategy_caps]
                        if missing_caps:
                            preview = ", ".join(missing_caps[:8])
                            suffix = "" if len(missing_caps) <= 8 else f", ... +{len(missing_caps) - 8} more"
                            blocking.append(
                                f"budget plan planned task budgets for {strategy_name} "
                                f"are missing selected tasks: {preview}{suffix}"
                            )
                        invalid_caps: list[str] = []
                        for task_id in task_ids:
                            if task_id not in strategy_caps:
                                continue
                            try:
                                cap = float(strategy_caps.get(task_id))
                            except (TypeError, ValueError):
                                invalid_caps.append(f"{task_id}=non_numeric")
                                continue
                            if not math.isfinite(cap) or cap <= 0:
                                invalid_caps.append(f"{task_id}={cap}")
                        if invalid_caps:
                            preview = ", ".join(invalid_caps[:8])
                            suffix = "" if len(invalid_caps) <= 8 else f", ... +{len(invalid_caps) - 8} more"
                            blocking.append(
                                f"budget plan planned task budgets for {strategy_name} "
                                f"must be finite positive USD values: {preview}{suffix}"
                            )

            task_level_strategy_names = [
                strategy.name for strategy in strategies if strategy.routing == "value_aware_task_level"
            ]
            frontier_diagnostic = bp.get("frontier_diagnostic")
            frontier_posture = (
                str(frontier_diagnostic.get("posture") or "")
                if isinstance(frontier_diagnostic, dict)
                else ""
            )
            if task_level_strategy_names:
                projection_diagnostics = bp.get("projection_diagnostics")
                task_diag = (
                    projection_diagnostics.get("budgetflow_task_level")
                    if isinstance(projection_diagnostics, dict)
                    else None
                )
                if not isinstance(task_diag, dict):
                    blocking.append(
                        "BudgetFlow task-level strategy is missing runtime projection diagnostics; "
                        "regenerate the budget plan with the current Budget Regime Compiler"
                    )
                else:
                    if "task_level_model_plan_source" in task_diag:
                        blocking.append(
                            "BudgetFlow task-level diagnostics use retired task_level_model_plan_source; "
                            "regenerate the budget plan with runtime_projection_source"
                        )
                    if "projected_tier_counts" in task_diag:
                        blocking.append(
                            "BudgetFlow task-level diagnostics use retired projected_tier_counts; "
                            "regenerate the budget plan with runtime_projected_tier_counts"
                        )
                    degeneration = str(task_diag.get("degeneration") or "")
                    stage_prefix_degeneration = str(task_diag.get("stage_prefix_degeneration") or "")
                    if degeneration in {"pure_reference_tier", "pure_strongest_tier"}:
                        blocking.append(
                            f"BudgetFlow task-level runtime projection degenerates to {degeneration}; "
                            "value-aware task-level paid runs must preserve a real T2/T3 frontier. "
                            "Use pure-tier baselines for fixed-tier controls or fix ModelFit/value/cost "
                            "calibration before paid run"
                        )
                    if stage_prefix_degeneration in {"pure_reference_tier", "pure_strongest_tier"}:
                        prefix_count = int(task_diag.get("stage_prefix_count") or 0)
                        blocking.append(
                            "BudgetFlow task-level staged prefix runtime projection degenerates to "
                            f"{stage_prefix_degeneration} over first {prefix_count} tasks; "
                            "10+10+10 paid runs must preserve a real T2/T3 frontier in the current "
                            "stage prefix or be relabeled as a pure-tier frontier diagnostic"
                        )

            active_revision = active_catalog_revision
            if active_catalog_path is None:
                blocking.append("active model tier catalog is not initialized")
                active_path = ""
            else:
                active_path = str(active_catalog_path)
            active_hash = str(catalog_source_info().get("catalog_content_hash") or "")
            facts.append(f"active_catalog_revision={active_revision}")
            facts.append(f"active_catalog_path={active_path}")
            facts.append(f"active_catalog_content_hash={active_hash}")
            bp_catalog_revision = str(bp.get("catalog_revision", "") or "")
            bp_catalog_path = str(bp.get("catalog_path", "") or "")
            bp_catalog_hash = str(bp.get("catalog_content_hash", "") or "")
            if bp_catalog_revision and active_revision and bp_catalog_revision != active_revision:
                blocking.append(
                    f"budget plan catalog_revision={bp_catalog_revision} does not match "
                    f"active catalog_revision={active_revision}"
                )
            if bp_catalog_path and active_path and Path(bp_catalog_path).resolve() != Path(active_path).resolve():
                blocking.append(
                    f"budget plan catalog_path={bp_catalog_path} does not match active catalog_path={active_path}"
                )
            if bp_catalog_hash and active_hash and bp_catalog_hash != active_hash:
                blocking.append(
                    f"budget plan catalog_content_hash={bp_catalog_hash} does not match "
                    f"active catalog_content_hash={active_hash}; regenerate the budget plan"
                )

    # ── Per-policy burn-rate deviation gate ───────────────────────────────
    if budget_plan_path is not None and budget_plan_path.is_file():
        try:
            import json as _json2
            bp2 = _json2.loads(budget_plan_path.read_text())
        except (OSError, ValueError, TypeError):
            bp2 = {}
        cal_err = bp2.get("calibration_error", {}) if isinstance(bp2, dict) else {}
        proj_conf = bp2.get("projection_confidence", "unvalidated") if isinstance(bp2, dict) else "unvalidated"
        per_strat_util = bp2.get("projected_utilization_by_strategy", {}) if isinstance(bp2, dict) else {}
        pressure_contract = bp2.get("pressure_contract", {}) if isinstance(bp2, dict) else {}
        frontier_diagnostic = bp2.get("frontier_diagnostic", {}) if isinstance(bp2, dict) else {}

        if proj_conf == "unvalidated":
            warnings.append(
                "budget plan projection_confidence=unvalidated: "
                "treat projected spend as diagnostic until a post-run audit validates it"
            )
        elif proj_conf == "low":
            warnings.append(
                "budget plan projection_confidence=low: "
                "treat projected utilization as advisory only"
            )

        # Check strongest baseline and both BF paper policies for large deviations
        gate_strategies = {"bare_t3_baseline", "budgetflow_task_level", "budgetflow_segment"}
        for gs in gate_strategies:
            gs_err = cal_err.get(gs) if cal_err else None
            if gs_err is not None and gs_err > 1.0:
                blocking.append(
                    f"calibration error for {gs} = {gs_err:.1%} > 100%; "
                    f"projection model is unreliable for primary paper strategies. "
                    f"Recalibrate budget compiler before paid run."
                )
            elif gs_err is not None and gs_err > 0.50:
                warnings.append(
                    f"calibration WARNING: {gs} projection error {gs_err:.1%} > 50%. "
                    f"treat the next run as diagnostic calibration evidence."
                )

        # Per-policy utilization: flag if strongest baseline or BF policies aren't budget-constrained
        t3_util = per_strat_util.get("bare_t3_baseline", 0.0) if per_strat_util else 0.0
        bf_task_util = per_strat_util.get("budgetflow_task_level", 0.0) if per_strat_util else 0.0
        bf_seg_util = per_strat_util.get("budgetflow_segment", 0.0) if per_strat_util else 0.0
        if t3_util < 0.10 and bf_task_util < 0.10 and bf_seg_util < 0.10:
            warnings.append(
                f"projected utilization too low for scarcity regime: "
                f"bare_t3={t3_util:.1%}, bf_task_level={bf_task_util:.1%}, bf_segment={bf_seg_util:.1%}. "
                f"Budget may be too loose for mechanism discrimination."
            )
        for violation in pressure_contract.get("violations", []) if isinstance(pressure_contract, dict) else []:
            if "budgetflow_task_level_degenerated" in str(violation):
                blocking.append(
                    "budget plan pressure contract has budgetflow_task_level_degenerated; "
                    "BudgetFlow task-level projection degenerates to a pure-tier frontier. "
                    "Use pure-tier baselines for fixed-tier controls or run as an explicit "
                    "frontier diagnostic — main evidence readiness must not silently pass "
                    "near-pure T2/T3 routing"
                )
                break
            if "budgetflow_task_level_stage_prefix_degenerated" in str(violation):
                blocking.append(
                    "budget plan pressure contract has budgetflow_task_level_stage_prefix_degenerated; "
                    "the staged prefix for this paid run is a pure-tier frontier. Regenerate "
                    "the plan, reorder tasks, or run it only as an explicit frontier diagnostic"
                )
                break
            if "budgetflow_under_target" in str(violation):
                warnings.append(
                    "budget plan pressure contract has budgetflow_under_target; "
                    "treat BudgetFlow projected utilization as a pressure warning"
                )
        if isinstance(frontier_diagnostic, dict):
            posture = str(frontier_diagnostic.get("posture") or "")
            if posture:
                facts.append(f"frontier_posture={posture}")
            if posture == "reference_cost_dominant":
                warnings.append(
                    "frontier diagnostic: reference tier is projected cheaper with weak ModelFit uplift; "
                    "treat the run as diagnostic for tier-boundary selection, not as strong tier-routing evidence"
                )
            elif posture == "strongest_cost_dominant":
                warnings.append(
                    "frontier diagnostic: Strongest Model is projected cost-dominant; "
                    "BudgetFlow must justify not collapsing to the strongest tier"
                )

    # ── Protocol health gate ───────────────────────────────────────────────
    existing_jsonl = _find_existing_jsonl(run_series, runs_dir)
    if existing_jsonl is not None:
        try:
            protocol_stats = _compute_protocol_health(existing_jsonl)
            facts.append(f"protocol_health_rows={protocol_stats['total_rows']}")
            facts.append(f"protocol_health_abort_rate={protocol_stats['protocol_abort_rate']:.1%}")
            facts.append(f"protocol_health_failed_retry_rate={protocol_stats['failed_protocol_retry_rate']:.1%}")
            facts.append(f"protocol_health_no_tool_call_rate={protocol_stats['no_tool_call_rate']:.1%}")
            if protocol_stats["protocol_abort_rate"] > 0.05:
                blocking.append(
                    f"protocol-owner abort rate {protocol_stats['protocol_abort_rate']:.1%} > 5%; "
                    f"action protocol is unstable — fix catalog protocol before paid run"
                )
            if protocol_stats["failed_protocol_retry_rate"] > 0.10:
                blocking.append(
                    f"failed protocol retry rate {protocol_stats['failed_protocol_retry_rate']:.1%} > 10%; "
                    f"excessive format failures — fix catalog protocol before paid run"
                )
            if protocol_stats["no_tool_call_rate"] > 0.10:
                blocking.append(
                    f"parser no-tool-call rate {protocol_stats['no_tool_call_rate']:.1%} > 10%; "
                    f"model/action protocol is unstable before paid run"
                )
        except (OSError, ValueError, TypeError) as exc:
            warnings.append(f"cannot compute protocol health from {existing_jsonl}: {exc}")
    else:
        facts.append("protocol_health=no_existing_jsonl")

    return ReadinessReport(tuple(blocking), tuple(warnings), tuple(facts))


def format_readiness_report(report: ReadinessReport) -> str:
    lines = ["=== PAID READINESS PREFLIGHT ==="]
    for fact in report.facts:
        lines.append(f"  {fact}")
    for warning in report.warnings:
        lines.append(f"  WARN: {warning}")
    for issue in report.blocking:
        lines.append(f"  BLOCK: {issue}")
    lines.append("  result=PASS" if report.ok else "  result=FAIL")
    return "\n".join(lines)
