"""Pre-provider readiness checks for BudgetFlow compare runs.

This module owns the launch-time contract for paid diagnostics. It does not
judge run outcomes; it only blocks runs whose setup would be hard to interpret.
"""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path

from budgetflow.experiments.compare_config import CompareStrategy
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
    facts.append(f"value_matrix={value_context.matrix_path or 'default_equal'}")
    facts.append(f"runtime_root={runtime_root}")
    facts.append("budget_mode=dynamic_task_caps" if auto_budget_caps else "budget_mode=static_or_shared")
    facts.append(f"auto_budget={'on' if auto_budget_enabled else 'off'}")
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
    elif any(strategy.routing in {"budgetflow_value_aware", "value_aware_task_level"} for strategy in strategies):
        warnings.append("value-aware strategy with equal task values supports T2/ablation, not T1 value evidence")

    if args.preset == "stage-split" and "value_aware_task_level_tight" not in strategy_names:
        blocking.append("stage-split preset must include value_aware_task_level_tight no-stage control")
    if args.task_set != "medium" and not args.ids and len(task_ids) <= 3:
        warnings.append("small familiar task set; diagnostic only, weak anti-overfitting evidence")
    if auto_budget_enabled and not auto_budget_caps:
        blocking.append("auto-budget enabled but no dynamic task caps were produced")
    if auto_budget_enabled and auto_budget_estimates:
        estimates = list(auto_budget_estimates.values())
        fallback_n = sum(1 for estimate in estimates if str(getattr(estimate, "source", "")) == "global_fallback")
        low_conf_n = sum(1 for estimate in estimates if str(getattr(estimate, "confidence", "")) == "low")
        if estimates and fallback_n == len(estimates):
            msg = "auto-budget caps are all global_fallback; do not claim Cost Memory lift"
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
            warnings.append(f"auto-budget caps mostly global_fallback ({fallback_n}/{len(estimates)}); cap learning is weak")
        if estimates and low_conf_n / len(estimates) >= 0.5:
            warnings.append(f"auto-budget estimates mostly low confidence ({low_conf_n}/{len(estimates)})")
    if not args.trace_turns:
        warnings.append("turn traces disabled; T3 Productive Rate/source breakdown will be weak")

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
