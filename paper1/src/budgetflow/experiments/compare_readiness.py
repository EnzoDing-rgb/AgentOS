"""Pre-provider readiness checks for BudgetFlow compare runs.

This module owns the launch-time contract for paid diagnostics. It does not
judge run outcomes; it only blocks runs whose setup would be hard to interpret.
"""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path

from budgetflow.experiments.compare_config import CompareStrategy
from budgetflow.frozen_router import load_frozen_plan
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
) -> ReadinessReport:
    blocking: list[str] = []
    warnings: list[str] = []
    facts: list[str] = []

    task_ids = [str(task.instance_id) for task in tasks]
    strategy_names = [strategy.name for strategy in strategies]

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
    facts.append("budget_mode=dynamic_task_caps" if auto_budget_caps else "budget_mode=static_or_shared")
    facts.append(f"dynamic_caps={'on' if auto_budget_enabled else 'off'}")
    if auto_budget_caps:
        planned_policy_cap = sum(float(cap) for cap in auto_budget_caps.values())
        facts.append(f"planned_policy_cap={planned_policy_cap:.4f}")
        facts.append(f"planned_total_cap={planned_policy_cap * max(len(strategy_names), 1):.4f}")

    if not task_ids:
        blocking.append("no tasks selected")
    if not strategy_names:
        blocking.append("no strategies selected")
    if len(strategy_names) > 1 and policy_jobs < len(strategy_names):
        blocking.append(
            f"policy_jobs={policy_jobs} is below strategy_count={len(strategy_names)}; "
            "policies must run in parallel and tasks serial within each policy"
        )
    if catalog_issues:
        blocking.extend(f"tier catalog: {issue}" for issue in catalog_issues)

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
    has_value_aware_strategy = any(
        strategy.routing in {"budgetflow_value_aware", "value_aware_task_level", "budgetflow_same_router"}
        for strategy in strategies
    )
    needs_frozen_plan = any(
        strategy.routing in {"enterprise_router", "budgetflow_same_router"}
        for strategy in strategies
    )
    if needs_frozen_plan and not args.frozen_plan:
        blocking.append(
            "enterprise_router_baseline and budgetflow_same_router require --frozen-plan"
        )
    elif needs_frozen_plan and args.frozen_plan:
        try:
            frozen_plan = load_frozen_plan(args.frozen_plan)
        except (OSError, ValueError, TypeError) as exc:
            blocking.append(f"cannot load frozen router plan: {exc}")
        else:
            facts.append(f"frozen_plan={frozen_plan.name}")
            facts.append(f"frozen_plan_entries={len(frozen_plan.plan)}")
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
    if has_value_aware_strategy and value_context.profile == "equal":
        warnings.append(
            "equal task values make value-aware strategies a T2 mechanism diagnostic, not T1 value evidence"
        )
    if has_value_aware_strategy and not value_context.is_primary_value_evidence:
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
