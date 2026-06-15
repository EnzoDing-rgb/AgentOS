"""Pre-provider readiness checks for BudgetFlow compare runs.

This module owns the launch-time contract for paid diagnostics. It does not
judge run outcomes; it only blocks runs whose setup would be hard to interpret.
"""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path

from budgetflow.experiments.compare_config import CompareStrategy, paper_mainline_strategy_names
from budgetflow.frozen_router import load_frozen_plan
from budgetflow.model_tiers import DEFAULT_CATALOG_PATH, catalog_path, catalog_revision
from budgetflow.value_efficiency import ValueEfficiencyContext


@dataclass(frozen=True)
class ReadinessReport:
    blocking: tuple[str, ...]
    warnings: tuple[str, ...]
    facts: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.blocking


def build_compare_readiness_report(
    *,
    args: Namespace,
    tasks: list,
    strategies: tuple[CompareStrategy, ...],
    policy_jobs: int,
    value_context: ValueEfficiencyContext,
    catalog_issues: list[str],
    runtime_root: Path,
    auto_budget_enabled: bool,
    auto_budget_caps: dict[str, float] | None,
    auto_budget_estimates: dict[str, object] | None = None,
    budget_plan_path: Path | None = None,
    per_task_cap: float | None = None,
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
    facts.append(f"value_profile={value_context.profile}")
    facts.append(f"value_source_class={value_context.source_class}")
    facts.append(f"value_evidence={value_context.evidence_role}")
    facts.append(f"value_confidence={value_context.confidence}")
    facts.append(f"value_primary_t1={str(value_context.is_primary_value_evidence).lower()}")
    facts.append(f"value_matrix={value_context.matrix_path or 'equal_sanity'}")
    facts.append(f"runtime_root={runtime_root}")
    mainline_strategy_names = list(paper_mainline_strategy_names())
    is_paper_mainline = strategy_names == mainline_strategy_names
    facts.append(f"paper_mainline={str(is_paper_mainline).lower()}")
    frozen_plan_arg = getattr(args, "frozen_plan", None)
    uses_frozen_plan_routing = any(
        strategy.routing in {"enterprise_router", "budgetflow_same_router"}
        for strategy in strategies
    )
    if auto_budget_caps:
        facts.append("budget_mode=dynamic_task_caps")
    elif use_fixed_per_task_cap:
        facts.append("budget_mode=per_task_cap")
    else:
        facts.append("budget_mode=shared_batch_hard_budget")
    facts.append(f"dynamic_caps={'on' if auto_budget_enabled else 'off'}")
    if auto_budget_caps:
        planned_policy_cap = sum(float(cap) for cap in auto_budget_caps.values())
        facts.append(f"planned_policy_cap={planned_policy_cap:.4f}")
        facts.append(f"planned_total_cap={planned_policy_cap * max(len(strategy_names), 1):.4f}")

    if not task_ids:
        blocking.append("no tasks selected")
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
    if not strategy_names:
        blocking.append("no strategies selected")
    if len(strategy_names) > 1 and policy_jobs < len(strategy_names):
        blocking.append(
            f"policy_jobs={policy_jobs} is below strategy_count={len(strategy_names)}; "
            "policies must run in parallel and tasks serial within each policy"
        )
    if catalog_issues:
        blocking.extend(f"tier catalog: {issue}" for issue in catalog_issues)
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
    if budget_plan_path is not None and auto_budget_enabled:
        blocking.append(
            "--budget-plan uses the Budget Regime Compiler shared-batch contract; "
            "--auto-budget enables retired dynamic per-task caps. Do not combine them."
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
        strategy.routing in {"enterprise_router", "budgetflow_same_router"}
        for strategy in strategies
    )
    if needs_frozen_plan and not frozen_plan_arg:
        blocking.append(
            "enterprise_router_baseline and budgetflow_same_enterprise_router require --frozen-plan"
        )
    elif needs_frozen_plan and frozen_plan_arg:
        try:
            frozen_plan = load_frozen_plan(frozen_plan_arg)
        except (OSError, ValueError, TypeError) as exc:
            blocking.append(f"cannot load frozen router plan: {exc}")
        else:
            selected_sum = frozen_plan.selected_cap_sum(task_ids) if task_ids else 0.0
            facts.append(f"frozen_plan={frozen_plan.name}")
            facts.append(f"frozen_plan_entries={len(frozen_plan.plan)}")
            facts.append(f"frozen_plan_planned_cap={frozen_plan.planned_cap:.4f}")
            facts.append(f"frozen_plan_selected_cap_sum={selected_sum:.4f}")
            if frozen_plan.hard_cap_usd is not None:
                facts.append(f"frozen_plan_hard_cap={frozen_plan.hard_cap_usd:.4f}")
                if abs(frozen_plan.planned_cap - frozen_plan.hard_cap_usd) > 0.0001:
                    blocking.append(
                        f"frozen plan base caps sum to {frozen_plan.planned_cap:.4f}, "
                        f"but meta hard_cap_usd={frozen_plan.hard_cap_usd:.4f}"
                    )
            requested_budget = float(getattr(args, "budget", 0.0) or 0.0)
            # When budget_plan provides the hard_cap (e.g. target_utilization mode),
            # the frozen cap sum is NOT the binding budget source.
            budget_is_from_plan = bool(requested_budget == 0.0 and getattr(args, "budget_plan", None))
            if budget_is_from_plan:
                facts.append("budget_source=budget_plan")
            elif requested_budget == 0.0:
                facts.append("budget_source=frozen_plan_cap_sum")
                facts.append(f"budget={selected_sum:.4f}")
            else:
                facts.append(f"budget_source=cli")
                facts.append(f"budget={requested_budget:.4f}")
                if abs(requested_budget - selected_sum) > 0.0001:
                    blocking.append(
                        f"--budget={requested_budget:.4f} does not match frozen plan "
                        f"selected cap sum={selected_sum:.4f}; "
                        "mechanism-isolation caps must be pre-registered and symmetric"
                    )
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
            "Yield numbers are T2 mechanism diagnostics, not T1 value evidence. "
            "Use a pre-registered manual value matrix for T1 claims."
        )
    if needs_task_values and value_context.profile == "equal":
        warnings.append(
            "equal task values make value-aware strategies a T2 mechanism diagnostic, not T1 value evidence"
        )
    if needs_task_values and not value_context.is_primary_value_evidence:
        warnings.append(
            f"value_source_kind={value_context.source_class} is not primary T1 evidence; "
            "use --value-source-kind pre_registered_manual with a frozen matrix for main Yield claims"
        )

    if args.task_set != "medium" and not args.ids and len(task_ids) <= 3:
        warnings.append("small familiar task set; diagnostic only, weak anti-overfitting evidence")
    if auto_budget_enabled and not auto_budget_caps:
        blocking.append("dynamic task caps enabled but no task caps were produced")
    if auto_budget_enabled and auto_budget_estimates:
        estimates = list(auto_budget_estimates.values())
        fallback_n = sum(1 for estimate in estimates if str(getattr(estimate, "source", "")) == "global_fallback")
        low_conf_n = sum(1 for estimate in estimates if str(getattr(estimate, "confidence", "")) == "low")
        if estimates and fallback_n == len(estimates):
            msg = "dynamic task caps are all global_fallback; do not claim Cost Memory lift"
            if (
                getattr(args, "allow_global_fallback_auto_budget", False)
                or getattr(args, "auto_budget_dry_run", False)
            ):
                warnings.append(msg)
            else:
                blocking.append(
                    msg
                    + "; pass --allow-global-fallback-auto-budget only for a fallback-cap diagnostic"
                )
        elif estimates and fallback_n / len(estimates) >= 0.5:
            warnings.append(f"dynamic task caps mostly global_fallback ({fallback_n}/{len(estimates)}); Cost Memory signal is weak")
        if estimates and low_conf_n / len(estimates) >= 0.5:
            warnings.append(f"dynamic cap estimates mostly low confidence ({low_conf_n}/{len(estimates)})")
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
            if not bp.get("generation_mode"):
                blocking.append(
                    "budget plan is missing generation_mode; regenerate it with the Budget Regime Compiler"
                )
            if bp_decision == "BLOCK":
                blocking.append(
                    f"budget plan decision is BLOCK: {'; '.join(bp_reasons)}"
                )
            elif bp_decision == "PASS_WITH_DIAGNOSTIC_OVERRIDE":
                override = bp.get("override_reason", "")
                warnings.append(
                    f"budget plan decision is PASS_WITH_DIAGNOSTIC_OVERRIDE: "
                    f"{'; '.join(bp_reasons)}"
                )
                if override:
                    facts.append(f"budget_plan_override: {override}")
            requested_budget = float(getattr(args, "budget", 0.0) or 0.0)
            if requested_budget > 0 and abs(requested_budget - bp_hard_cap) > 0.0001:
                blocking.append(
                    f"--budget={requested_budget:.4f} does not match "
                    f"budget_plan hard_cap={bp_hard_cap:.4f}; "
                    f"use the budget plan value or omit --budget"
                )
            bp_task_ids = bp.get("task_ids")
            if isinstance(bp_task_ids, list) and bp_task_ids:
                bp_task_set = {str(task_id) for task_id in bp_task_ids}
                facts.append(f"budget_plan_task_ids={len(bp_task_set)}")
                missing_budget_tasks = [task_id for task_id in task_ids if task_id not in bp_task_set]
                if missing_budget_tasks:
                    preview = ", ".join(missing_budget_tasks[:8])
                    suffix = "" if len(missing_budget_tasks) <= 8 else f", ... +{len(missing_budget_tasks) - 8} more"
                    blocking.append(
                        f"budget plan is missing {len(missing_budget_tasks)} selected tasks: "
                        f"{preview}{suffix}"
                    )
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

            active_revision = active_catalog_revision
            active_path = str(active_catalog_path) if active_catalog_path else "python_fallback"
            facts.append(f"active_catalog_revision={active_revision}")
            facts.append(f"active_catalog_path={active_path}")
            bp_catalog_revision = str(bp.get("catalog_revision", "") or "")
            bp_catalog_path = str(bp.get("catalog_path", "") or "")
            if bp_catalog_revision and active_revision and bp_catalog_revision != active_revision:
                blocking.append(
                    f"budget plan catalog_revision={bp_catalog_revision} does not match "
                    f"active catalog_revision={active_revision}"
                )
            if bp_catalog_path and active_path and Path(bp_catalog_path).resolve() != Path(active_path).resolve():
                blocking.append(
                    f"budget plan catalog_path={bp_catalog_path} does not match active catalog_path={active_path}"
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

        if proj_conf == "unvalidated":
            warnings.append(
                "budget plan projection_confidence=unvalidated: "
                "do not claim target utilization or scarcity regime is satisfied"
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
                    f"Consider wider safety margin or frozen_plan_cap_sum mode."
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
