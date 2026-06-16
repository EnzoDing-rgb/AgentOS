"""Built-in Routing and Escalation Memory for Learn Policy.

This module rebuilds compact priors from verified run JSONL. It is a built-in
Memory backend, not part of the BudgetFlow Mechanism and not the only possible learning method.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .defaults import POLICY_REGRET_THRESHOLD
from .failure_classification import SCOREABLE_STATUSES, is_scoreable
from .model_tiers import parse_tier_label
from .types import WorkflowSegment


def _extract_repo(instance_id: str) -> str:
    return instance_id.split("__")[0] if "__" in instance_id else instance_id


@dataclass
class TaskContext:
    repo: str
    instance_id: str
    task_type: str = "swebench"
    difficulty: str = "unknown"
    value: float = 1.0
    deadline: float | None = None
    account_id: str = "default"

    @classmethod
    def from_instance_id(cls, instance_id: str) -> TaskContext:
        return cls(repo=_extract_repo(instance_id), instance_id=instance_id)


@dataclass
class BudgetAccount:
    account_id: str = "default"
    window_id: str = "default"
    remaining_budget: float = float("inf")


@dataclass
class RepoPrior:
    repo: str
    total_tasks: int = 0
    pass_count: float = 0.0
    evidence_weight: float = 0.0
    tier_turns: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    tier_success_rate: dict[int, float] = field(default_factory=dict)
    median_cost: float = 0.0
    failure_classes: Counter = field(default_factory=Counter)
    segment_tier_success: dict[str, dict[int, float]] = field(default_factory=lambda: defaultdict(dict))
    segment_tier_weight: dict[str, dict[int, float]] = field(default_factory=lambda: defaultdict(dict))

    @property
    def t2_turns(self) -> int:
        return self.tier_turns.get(2, 0)

    @property
    def t3_turns(self) -> int:
        return self.tier_turns.get(3, 0)

    @property
    def t2_success_rate(self) -> float:
        return self.tier_success_rate.get(2, 0.0)

    @property
    def t3_success_rate(self) -> float:
        return self.tier_success_rate.get(3, 0.0)

    @property
    def t2_segment_success(self) -> dict[str, float]:
        return {stage: by_tier.get(2, 0.0) for stage, by_tier in self.segment_tier_success.items()}

    @property
    def t3_segment_success(self) -> dict[str, float]:
        return {stage: by_tier.get(3, 0.0) for stage, by_tier in self.segment_tier_success.items()}


@dataclass
class TaskPrior:
    instance_id: str
    repo: str = ""
    seen: int = 0
    pass_count: float = 0.0
    evidence_weight: float = 0.0
    median_cost: float = 0.0
    all_pro_failures: float = 0.0
    tier_turns: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    failure_classes: Counter = field(default_factory=Counter)

    def __post_init__(self) -> None:
        if not self.repo:
            self.repo = _extract_repo(self.instance_id)


@dataclass
class PolicyRegret:
    repo: str
    full_cost: float = 0.0
    baseline_cost: float = 0.0
    full_pass: float = 0.0
    baseline_pass: float = 0.0
    full_count: float = 0.0
    baseline_count: float = 0.0
    regret: float = 0.0  # positive = full more expensive without more passes

    @property
    def full_avg_cost(self) -> float:
        return self.full_cost / max(self.full_count, 1)

    @property
    def baseline_avg_cost(self) -> float:
        return self.baseline_cost / max(self.baseline_count, 1)


@dataclass
class EscalationPrior:
    """Learn whether value-triggered T3 escalation paid off in prior traces."""

    attempts: float = 0.0
    resolved: float = 0.0
    t3_turns: float = 0.0
    t3_productive_turns: float = 0.0
    t3_no_progress_cost: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.resolved / max(self.attempts, 1)

    @property
    def t3_productive_rate(self) -> float:
        return self.t3_productive_turns / max(self.t3_turns, 1)


@dataclass
class StarterPrior:
    """Learn whether a short strongest-tier starter window beat delayed rescue."""

    attempts: float = 0.0
    budgetflow_failures: float = 0.0
    budget_only_successes: float = 0.0
    budgetflow_expensive_successes: float = 0.0
    bo_success_cost: float = 0.0
    budgetflow_success_cost: float = 0.0
    bo_frontload_t3_turns: float = 0.0
    bo_total_turns: float = 0.0
    budgetflow_starter_attempts: float = 0.0
    budgetflow_starter_successes: float = 0.0
    budgetflow_starter_failures: float = 0.0
    budgetflow_starter_t3_turns: float = 0.0
    budgetflow_starter_productive_turns: float = 0.0
    budgetflow_starter_no_progress_cost: float = 0.0

    @property
    def bo_frontload_rate(self) -> float:
        return self.bo_frontload_t3_turns / max(self.bo_total_turns, 1e-9)

    @property
    def success_cost_ratio(self) -> float:
        if self.bo_success_cost <= 0:
            return 0.0
        return self.budgetflow_success_cost / self.bo_success_cost

    @property
    def budgetflow_starter_productive_rate(self) -> float:
        return self.budgetflow_starter_productive_turns / max(self.budgetflow_starter_t3_turns, 1)

    @property
    def budgetflow_starter_success_rate(self) -> float:
        return self.budgetflow_starter_successes / max(self.budgetflow_starter_attempts, 1)


# ── record acceptance for memory ────────────────────────────────────────────

# Routings that are supported for memory learning.
_MEMORY_ROUTINGS = frozenset({
    "budgetflow_segment", "budgetflow_conservative", "segment_value_aware",
    "value_aware_task_level", "budgetflow_equal_weight", "stage_blind",
    "budget_only", "bare_t3_baseline", "enterprise_router_baseline",
    "budgetflow_same_router",
})

# Harness trust values that are acceptable for memory.
_MEMORY_HARNESS_TRUST = frozenset({"trusted", "trusted_fallback"})


def _memory_skip_reason(record: dict) -> str:
    """Return a non-empty reason string if *record* should NOT enter memory.

    Returns "" if the record is acceptable.
    """
    # Schema version
    if record.get("routing_decision_schema") != "v1":
        return "old_schema"
    # Score status: only pass and true_fail are scoreable
    score = str(record.get("score_status") or "")
    if score not in SCOREABLE_STATUSES:
        if score == "abort":
            return "abort_row"
        return "unscoreable_status"
    # Must have instance_id
    if not record.get("instance_id"):
        return "missing_instance_id"
    # Routing must be in supported set
    routing = str(record.get("routing") or "")
    if routing not in _MEMORY_ROUTINGS:
        return f"unsupported_routing:{routing}" if routing else "missing_routing"
    # Harness trust: reject protocol/parser aborts
    harness_trust = str(record.get("harness_trust") or "")
    if harness_trust not in _MEMORY_HARNESS_TRUST:
        if harness_trust == "incomplete":
            return "harness_incomplete"
        if harness_trust:
            return f"harness_trust:{harness_trust}"
        return "missing_harness_trust"
    # Must have task_set_kind and policy_kind
    if not record.get("task_set_kind"):
        return "missing_task_set_kind"
    if not record.get("policy_kind"):
        return "missing_policy_kind"
    # Must have learn_policy_input_views
    views = record.get("learn_policy_input_views")
    if not isinstance(views, list) or not views:
        return "missing_learn_policy_views"
    # Exclude host dependency contamination
    detail = str(record.get("detail") or "")
    if "has_host_dependency_contamination" in detail:
        return "host_dependency_contamination"
    return ""


class PolicyMemory:
    """Built-in Routing/Escalation Memory rebuilt from JSONL outcomes.

    Consumes verified task records (harness_resolved, total_cost, turn_traces,
    failure_class, backend_picks). The outputs are priors that a Learn Policy
    may consume through the PolicyBackend boundary.
    """

    def __init__(self, ewma_alpha: float = 0.3, window_size: int = 20, regret_threshold: float | None = None):
        self._ewma_alpha = ewma_alpha
        self._window_size = window_size
        self.regret_threshold = regret_threshold if regret_threshold is not None else POLICY_REGRET_THRESHOLD
        self._repo_priors: dict[str, RepoPrior] = {}
        self._task_priors: dict[str, TaskPrior] = {}
        self._policy_regrets: dict[str, PolicyRegret] = {}
        self._repo_escalation: dict[str, EscalationPrior] = {}
        self._task_escalation: dict[str, EscalationPrior] = {}
        self._repo_starters: dict[str, StarterPrior] = {}
        self._task_starters: dict[str, StarterPrior] = {}
        self._record_count: int = 0
        self._effective_record_weight: float = 0.0
        self._source_weight_summary: dict[str, float] = {}
        self._source_path: str = ""
        # Memory filtering audit fields
        self._records_seen: int = 0
        self._records_accepted: int = 0
        self._records_skipped: int = 0
        self._skip_reasons: dict[str, int] = {}

    # ── rebuild ────────────────────────────────────────────────────────────

    def rebuild_from_jsonl(self, path: Path) -> None:
        """Clear all priors and rebuild from a JSONL file."""
        self._source_path = str(path)
        if not path.is_file():
            return
        records: list[dict] = []
        for line in path.read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        self.rebuild_from_records(records)

    def rebuild_from_records(self, records: list[dict]) -> None:
        """Rebuild all priors from a list of outcome records.

        Only rows that pass the schema-aware acceptance filter contribute to
        Cost/Routing/Escalation Memory. Skipped rows are tracked for audit.
        """
        self._repo_priors.clear()
        self._task_priors.clear()
        self._policy_regrets.clear()
        self._repo_escalation.clear()
        self._task_escalation.clear()
        self._repo_starters.clear()
        self._task_starters.clear()
        self._record_count = len(records)

        accepted: list[dict] = []
        skip_reasons: Counter[str] = Counter()
        for record in records:
            reason = _memory_skip_reason(record)
            if reason:
                skip_reasons[reason] += 1
            else:
                accepted.append(record)

        self._records_seen = len(records)
        self._records_accepted = len(accepted)
        self._records_skipped = self._records_seen - self._records_accepted
        self._skip_reasons = dict(skip_reasons)

        learnable_records = [
            record for record in accepted
            if str(record.get("score_status") or "") in SCOREABLE_STATUSES
        ]
        self._effective_record_weight = round(sum(_record_weight(record) for record in learnable_records), 4)
        source_weights: dict[str, float] = defaultdict(float)
        for record in learnable_records:
            source = str(record.get("_policy_memory_source") or "unknown")
            source_weights[source] += _record_weight(record)
        self._source_weight_summary = {source: round(weight, 4) for source, weight in sorted(source_weights.items())}

        # Group by repo
        repo_records: dict[str, list[dict]] = defaultdict(list)
        task_records: dict[str, list[dict]] = defaultdict(list)
        for r in learnable_records:
            iid = str(r.get("instance_id") or "")
            if not iid:
                continue
            repo = _extract_repo(iid)
            repo_records[repo].append(r)
            task_records[iid].append(r)

        # Build repo priors
        for repo, recs in repo_records.items():
            self._repo_priors[repo] = self._build_repo_prior(repo, recs)

        # Build task priors
        for iid, recs in task_records.items():
            self._task_priors[iid] = self._build_task_prior(iid, recs)

        # Build policy regrets
        for repo, recs in repo_records.items():
            self._policy_regrets[repo] = self._build_policy_regret(repo, recs)
            self._repo_escalation[repo] = self._build_escalation_prior(recs)
            self._repo_starters[repo] = self._build_starter_prior(recs)
        for iid, recs in task_records.items():
            self._task_escalation[iid] = self._build_escalation_prior(recs)
            self._task_starters[iid] = self._build_starter_prior(recs)

    def _build_repo_prior(self, repo: str, records: list[dict]) -> RepoPrior:
        prior = RepoPrior(repo=repo)
        prior.total_tasks = len({r.get("instance_id") for r in records})
        prior.evidence_weight = round(sum(_record_weight(r) for r in records), 4)
        prior.pass_count = round(sum(_record_weight(r) for r in records if r.get("harness_resolved")), 4)

        costs = sorted(float(r.get("total_cost") or 0) for r in records)
        if costs:
            mid = len(costs) // 2
            prior.median_cost = costs[mid] if len(costs) % 2 else (costs[mid - 1] + costs[mid]) / 2

        tier_pass: dict[int, float] = defaultdict(float)
        tier_total: dict[int, float] = defaultdict(float)
        segment_tier_pass: dict[str, dict[int, list[tuple[float, float]]]] = defaultdict(lambda: defaultdict(list))

        for r in records:
            picks = r.get("backend_picks") or []
            tiers_seen: set[int] = set()
            for pick in picks:
                tier = _pick_tier(pick)
                if tier > 0:
                    prior.tier_turns[tier] += 1
                    tiers_seen.add(tier)
            passed = bool(r.get("harness_resolved"))
            weight = _record_weight(r)
            for tier in tiers_seen:
                tier_total[tier] += weight
                tier_pass[tier] += weight if passed else 0

            prior.failure_classes[str(r.get("failure_class") or "unknown")] += weight

            # Segment-level priors from turn_traces
            traces = r.get("turn_traces") or []
            segments_by_tier: dict[int, set[str]] = defaultdict(set)
            for t in traces:
                segment = _trace_segment_key(t)
                tier = t.get("backend_tier")
                if not segment:
                    continue
                try:
                    tier_int = int(tier)
                except (TypeError, ValueError):
                    continue
                if tier_int > 0:
                    segments_by_tier[tier_int].add(segment)
            for tier, segments in segments_by_tier.items():
                for segment in segments:
                    segment_tier_pass[segment][tier].append((weight if passed else 0.0, weight))

        prior.tier_success_rate = {
            tier: tier_pass[tier] / max(tier_total[tier], 1e-9)
            for tier in sorted(tier_total)
        }
        prior.segment_tier_success = defaultdict(dict)
        for stage, by_tier in segment_tier_pass.items():
            prior.segment_tier_success[stage] = {
                tier: sum(pass_weight for pass_weight, _ in values) / max(sum(total_weight for _, total_weight in values), 1e-9)
                for tier, values in sorted(by_tier.items())
            }
            prior.segment_tier_weight[stage] = {
                tier: round(sum(total_weight for _, total_weight in values), 4)
                for tier, values in sorted(by_tier.items())
            }
        return prior

    def _build_task_prior(self, instance_id: str, records: list[dict]) -> TaskPrior:
        prior = TaskPrior(instance_id=instance_id)
        prior.seen = len(records)
        prior.evidence_weight = round(sum(_record_weight(r) for r in records), 4)
        prior.pass_count = round(sum(_record_weight(r) for r in records if r.get("harness_resolved")), 4)

        costs = sorted(float(r.get("total_cost") or 0) for r in records)
        if costs:
            mid = len(costs) // 2
            prior.median_cost = costs[mid] if len(costs) % 2 else (costs[mid - 1] + costs[mid]) / 2

        for r in records:
            weight = _record_weight(r)
            prior.failure_classes[str(r.get("failure_class") or "unknown")] += weight
            if r.get("strategy") == "all_pro":
                if not r.get("harness_resolved"):
                    prior.all_pro_failures += weight
            picks = r.get("backend_picks") or []
            for p in picks:
                tier = _pick_tier(p)
                if tier > 0:
                    prior.tier_turns[tier] += 1
        return prior

    def _build_policy_regret(self, repo: str, records: list[dict]) -> PolicyRegret:
        regret = PolicyRegret(repo=repo)
        # Group by instance_id to compare full vs baseline
        by_task: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
        for r in records:
            iid = str(r.get("instance_id") or "")
            routing = str(r.get("routing") or "")
            if routing in ("budgetflow_segment", "budgetflow_conservative", "segment_value_aware", "value_aware_task_level") or "budgetflow_segment" in routing:
                by_task[iid]["full"].append(r)
            elif "budget_only" in routing:
                by_task[iid]["baseline"].append(r)

        for iid, groups in by_task.items():
            full_recs = groups.get("full", [])
            baseline_recs = groups.get("baseline", [])
            if not full_recs or not baseline_recs:
                continue
            regret.full_count += _weighted_count(full_recs)
            regret.baseline_count += _weighted_count(baseline_recs)
            regret.full_cost += _weighted_cost(full_recs)
            regret.baseline_cost += _weighted_cost(baseline_recs)
            regret.full_pass += sum(_record_weight(r) for r in full_recs if r.get("harness_resolved"))
            regret.baseline_pass += sum(_record_weight(r) for r in baseline_recs if r.get("harness_resolved"))

        if regret.baseline_count > 0 and regret.full_count > 0:
            full_avg = regret.full_avg_cost
            baseline_avg = regret.baseline_avg_cost
            full_rate = regret.full_pass / max(regret.full_count, 1)
            baseline_rate = regret.baseline_pass / max(regret.baseline_count, 1)
            if full_rate <= baseline_rate and full_avg > baseline_avg:
                regret.regret = full_avg - baseline_avg
            elif full_avg > baseline_avg * 1.3:
                regret.regret = (full_avg - baseline_avg) / baseline_avg
        return regret

    def _build_escalation_prior(self, records: list[dict]) -> EscalationPrior:
        prior = EscalationPrior()
        for record in records:
            if str(record.get("routing") or "") not in {"segment_value_aware", "value_aware_task_level"}:
                continue
            traces = record.get("turn_traces") or []
            if not isinstance(traces, list):
                continue
            escalation_traces = [
                trace for trace in traces
                if isinstance(trace, dict) and _trace_has_value_triggered_escalation(trace)
            ]
            if not escalation_traces:
                continue
            weight = _record_weight(record)
            prior.attempts += weight
            if record.get("harness_resolved"):
                prior.resolved += weight
            for trace in escalation_traces:
                if _trace_tier(trace) < 3:
                    continue
                prior.t3_turns += weight
                productive = _trace_productivity(trace)
                if productive is True:
                    prior.t3_productive_turns += weight
                elif productive is False:
                    prior.t3_no_progress_cost += weight * float(
                        trace.get("billable_cost") or trace.get("actual_cost") or 0.0
                    )
        return prior

    def _build_starter_prior(self, records: list[dict]) -> StarterPrior:
        prior = StarterPrior()
        by_task: dict[str, list[dict]] = defaultdict(list)
        for record in records:
            iid = str(record.get("instance_id") or "")
            if iid:
                by_task[iid].append(record)

        for task_records in by_task.values():
            budget_only = [
                record for record in task_records
                if str(record.get("routing") or "") == "budget_only"
            ]
            budgetflow = [
                record for record in task_records
                if str(record.get("routing") or "") in {
                    "budgetflow_conservative",
                    "segment_value_aware",
                    "value_aware_task_level",
                    "budgetflow_segment",
                }
            ]
            for record in budgetflow:
                traces = [trace for trace in (record.get("turn_traces") or []) if isinstance(trace, dict)]
                starter_traces = [
                    trace for trace in traces
                    if trace.get("strongest_starter_applied") and _trace_tier(trace) >= 3
                ]
                if starter_traces:
                    weight = _record_weight(record)
                    prior.budgetflow_starter_attempts += weight
                    if record.get("harness_resolved"):
                        prior.budgetflow_starter_successes += weight
                    else:
                        prior.budgetflow_starter_failures += weight
                    for trace in starter_traces:
                        prior.budgetflow_starter_t3_turns += weight
                        productive = _trace_productivity(trace)
                        if productive is True:
                            prior.budgetflow_starter_productive_turns += weight
                        elif productive is False:
                            prior.budgetflow_starter_no_progress_cost += weight * float(
                                trace.get("billable_cost") or trace.get("actual_cost") or 0.0
                            )
            if not budget_only or not budgetflow:
                continue

            bo_success_weight = sum(_record_weight(record) for record in budget_only if record.get("harness_resolved"))
            bf_fail_weight = sum(_record_weight(record) for record in budgetflow if not record.get("harness_resolved"))
            bf_success = [record for record in budgetflow if record.get("harness_resolved")]
            bf_success_weight = sum(_record_weight(record) for record in bf_success)
            bo_success_cost = sum(
                _record_weight(record) * float(record.get("total_cost") or 0.0)
                for record in budget_only if record.get("harness_resolved")
            )
            bf_success_cost = sum(
                _record_weight(record) * float(record.get("total_cost") or 0.0)
                for record in bf_success
            )
            expensive_success_weight = 0.0
            if bo_success_weight > 0 and bf_success_weight > 0 and bo_success_cost > 0:
                bo_avg = bo_success_cost / bo_success_weight
                bf_avg = bf_success_cost / bf_success_weight
                if bf_avg >= bo_avg * 2.5 and (bf_avg - bo_avg) >= 0.10:
                    expensive_success_weight = min(bo_success_weight, bf_success_weight)

            matched_weight = min(bo_success_weight, bf_fail_weight) + expensive_success_weight
            if matched_weight <= 0:
                continue

            prior.attempts += matched_weight
            prior.budget_only_successes += bo_success_weight
            prior.budgetflow_failures += bf_fail_weight
            prior.budgetflow_expensive_successes += expensive_success_weight
            prior.bo_success_cost += bo_success_cost
            prior.budgetflow_success_cost += bf_success_cost
            for record in budget_only:
                if not record.get("harness_resolved"):
                    continue
                weight = _record_weight(record)
                traces = [trace for trace in (record.get("turn_traces") or []) if isinstance(trace, dict)]
                early = traces[: min(8, len(traces))]
                prior.bo_total_turns += weight * len(early)
                prior.bo_frontload_t3_turns += weight * sum(1 for trace in early if _trace_tier(trace) >= 3)
        return prior

    # ── query ──────────────────────────────────────────────────────────────

    def repo_prior(self, instance_id: str) -> RepoPrior:
        repo = _extract_repo(instance_id)
        return self._repo_priors.get(repo, RepoPrior(repo=repo))

    def task_prior(self, instance_id: str) -> TaskPrior:
        return self._task_priors.get(instance_id, TaskPrior(instance_id=instance_id))

    def policy_regret(self, instance_id: str) -> PolicyRegret | None:
        repo = _extract_repo(instance_id)
        return self._policy_regrets.get(repo)

    def escalation_prior(self, instance_id: str) -> tuple[EscalationPrior, str]:
        task_prior = self._task_escalation.get(instance_id)
        if task_prior is not None and task_prior.attempts > 0:
            return task_prior, "task"
        repo = _extract_repo(instance_id)
        return self._repo_escalation.get(repo, EscalationPrior()), "repo"

    def starter_prior(self, instance_id: str) -> tuple[StarterPrior, str]:
        task_prior = self._task_starters.get(instance_id)
        if task_prior is not None and _starter_action_evidence_weight(task_prior) >= 1.0:
            return task_prior, "task"
        repo = _extract_repo(instance_id)
        return self._repo_starters.get(repo, StarterPrior()), "repo"

    def routing_prior_summary(self, instance_id: str, segment: str | None = None) -> dict:
        repo = self.repo_prior(instance_id)
        task = self.task_prior(instance_id)
        regret = self.policy_regret(instance_id)

        # Determine learned action
        action = self._learned_action(instance_id, segment)
        escalation, escalation_source = self.escalation_prior(instance_id)
        escalation_action, escalation_window = _escalation_action(escalation)
        starter, starter_source = self.starter_prior(instance_id)
        starter_action, starter_window = _starter_action(starter, starter_source)

        # Top failure class for task
        task_top_failure = ""
        if task.failure_classes:
            non_pass = [(k, v) for k, v in task.failure_classes.items() if k != "pass"]
            if non_pass:
                task_top_failure = max(non_pass, key=lambda x: x[1])[0]

        summary: dict = {
            "repo": repo.repo,
            "repo_t2_success": round(repo.t2_success_rate, 3),
            "repo_t3_success": round(repo.t3_success_rate, 3),
            "repo_tier_success": {str(k): round(v, 3) for k, v in sorted(repo.tier_success_rate.items())},
            "repo_tier_turns": {str(k): v for k, v in sorted(repo.tier_turns.items())},
            "repo_tasks": repo.total_tasks,
            "repo_evidence_weight": repo.evidence_weight,
            "repo_median_cost": round(repo.median_cost, 4),
            "task_seen": task.seen,
            "task_evidence_weight": task.evidence_weight,
            "task_pass_count": task.pass_count,
            "task_pass_weight": task.pass_count,
            "task_median_cost": round(task.median_cost, 4),
            "task_all_pro_failures": task.all_pro_failures,
            "task_all_pro_failure_weight": task.all_pro_failures,
            "recent_failure_axis": task_top_failure,
            "full_vs_baseline_regret": round(regret.regret if regret else 0, 3),
            "learned_action": action,
            "regret_threshold": self.regret_threshold,
            "policy_memory_source": self._source_path or "",
            "policy_memory_effective_weight": self._effective_record_weight,
            "policy_memory_source_weights": self._source_weight_summary,
            "escalation_memory_source": escalation_source if escalation.attempts else "",
            "escalation_attempts": escalation.attempts,
            "escalation_success_rate": round(escalation.success_rate, 3),
            "t3_productive_rate": round(escalation.t3_productive_rate, 3),
            "t3_no_progress_cost": round(escalation.t3_no_progress_cost, 4),
            "value_triggered_escalation_action": escalation_action,
            "value_triggered_escalation_window": escalation_window,
            "starter_attempts": starter.attempts,
            "starter_memory_source": starter_source if starter.attempts else "",
            "starter_bo_success_weight": starter.budget_only_successes,
            "starter_budgetflow_failure_weight": starter.budgetflow_failures,
            "starter_budgetflow_expensive_success_weight": starter.budgetflow_expensive_successes,
            "starter_success_cost_ratio": round(starter.success_cost_ratio, 3),
            "starter_bo_frontload_rate": round(starter.bo_frontload_rate, 3),
            "starter_budgetflow_applied_weight": starter.budgetflow_starter_attempts,
            "starter_budgetflow_applied_success_weight": starter.budgetflow_starter_successes,
            "starter_budgetflow_applied_failure_weight": starter.budgetflow_starter_failures,
            "starter_budgetflow_success_rate": round(starter.budgetflow_starter_success_rate, 3),
            "starter_budgetflow_t3_productive_rate": round(starter.budgetflow_starter_productive_rate, 3),
            "starter_budgetflow_t3_no_progress_cost": round(starter.budgetflow_starter_no_progress_cost, 4),
            "strongest_starter_action": starter_action,
            "strongest_starter_window": starter_window,
        }
        if segment:
            summary["segment_t2_success"] = round(repo.t2_segment_success.get(segment, 0), 3)
            summary["segment_t3_success"] = round(repo.t3_segment_success.get(segment, 0), 3)
            summary["segment_tier_success"] = {
                str(k): round(v, 3)
                for k, v in sorted(repo.segment_tier_success.get(segment, {}).items())
            }
            summary["segment_tier_weight"] = {
                str(k): round(v, 4)
                for k, v in sorted(repo.segment_tier_weight.get(segment, {}).items())
            }
        return summary

    def _learned_action(self, instance_id: str, segment: str | None) -> str:
        repo = self.repo_prior(instance_id)
        task = self.task_prior(instance_id)
        regret = self.policy_regret(instance_id)

        # Rule 5: extract_fail/format_error → protocol issue
        top_failures = [k for k, _ in task.failure_classes.most_common(3) if k != "pass"]
        protocol_fails = {"extract_fail", "format_error", "parser_fail"}
        protocol_failure_weight = sum(task.failure_classes.get(failure, 0.0) for failure in protocol_fails)
        if protocol_failure_weight >= 1.0 and any(f in protocol_fails for f in top_failures):
            return "protocol_issue"

        # Rule 4: all_pro repeated failures → reduce rescue
        if task.all_pro_failures >= 2:
            return "reduce_rescue"

        # Rule 3: full vs baseline regret → cap strongest-tier rescue
        if regret and regret.regret > self.regret_threshold and regret.full_count >= 2:
            return "cap_strongest"

        repair_key = WorkflowSegment.ACTION
        loc_key = WorkflowSegment.CONTEXT

        # Rule 1: second-tier repair success low → early strongest-tier rescue
        if segment == WorkflowSegment.ACTION or segment is None:
            t2_repair = repo.t2_segment_success.get(repair_key, 0)
            t2_repair_weight = repo.segment_tier_weight.get(repair_key, {}).get(2, 0.0)
            if t2_repair < 0.35 and t2_repair_weight >= 3.0:
                return "early_rescue"

        # Rule 2: second-tier localization good → skip cheapest on start
        if segment == WorkflowSegment.CONTEXT:
            t2_loc = repo.t2_segment_success.get(loc_key, 0)
            t2_loc_weight = repo.segment_tier_weight.get(loc_key, {}).get(2, 0.0)
            if t2_loc > 0.55 and t2_loc_weight >= 2.0:
                return "start_second_cheapest"

        return "default"

    # ── write-through ──────────────────────────────────────────────────────

    def record_outcome(self, record: dict) -> None:
        """Incrementally update priors after a single task completes."""
        if not is_scoreable(record):
            return
        iid = str(record.get("instance_id") or "")
        if not iid:
            return
        repo_key = _extract_repo(iid)

        # Update task prior
        old_task = self._task_priors.get(iid)
        if old_task:
            new_records = [record]  # we'd need old records too; just use EWMA blend
            self._task_priors[iid] = self._blend_task_prior(old_task, record)
        else:
            self._task_priors[iid] = self._build_task_prior(iid, [record])

        # Rebuild repo prior (cheap — at most window_size records)
        self._record_count += 1
        # For simplicity, just mark as dirty; full rebuild on next resume
        # In a real system we'd maintain a sliding window.

    def _blend_task_prior(self, old: TaskPrior, record: dict) -> TaskPrior:
        """EWMA-blend a new outcome into an existing task prior."""
        a = self._ewma_alpha
        prior = TaskPrior(instance_id=old.instance_id)
        prior.seen = old.seen + 1
        record_weight = _record_weight(record)
        prior.evidence_weight = round(old.evidence_weight + record_weight, 4)
        passed = bool(record.get("harness_resolved"))
        prior.pass_count = old.pass_count + (record_weight if passed else 0)
        new_cost = float(record.get("total_cost") or 0)
        prior.median_cost = a * new_cost + (1 - a) * old.median_cost
        prior.all_pro_failures = old.all_pro_failures + (
            record_weight if record.get("strategy") == "all_pro" and not passed else 0
        )
        prior.tier_turns = defaultdict(int, old.tier_turns)
        for p in record.get("backend_picks") or []:
            tier = _pick_tier(p)
            if tier > 0:
                prior.tier_turns[tier] += 1
        prior.failure_classes = Counter(old.failure_classes)
        prior.failure_classes[str(record.get("failure_class") or "unknown")] += record_weight
        return prior

    # ── summary ────────────────────────────────────────────────────────────

    @property
    def memory_filtering_summary(self) -> dict:
        """Return audit summary of memory record acceptance."""
        return {
            "memory_source": self._source_path,
            "schema_version": "v1",
            "active_views": ["cost", "routing", "escalation"],
            "records_seen": self._records_seen,
            "records_accepted": self._records_accepted,
            "records_skipped": self._records_skipped,
            "skip_reasons": dict(self._skip_reasons),
        }

    def summary_lines(self) -> list[str]:
        lines = ["policy_memory:"]
        lines.append(
            f"  records={self._record_count} effective_weight={self._effective_record_weight:.2f} "
            f"repos={len(self._repo_priors)} tasks={len(self._task_priors)}"
        )
        if self._records_skipped:
            lines.append(
                f"  filtering: seen={self._records_seen} accepted={self._records_accepted} "
                f"skipped={self._records_skipped} skip_reasons={dict(self._skip_reasons)}"
            )
        for repo, prior in sorted(self._repo_priors.items()):
            lines.append(
                f"  {repo}: tasks={prior.total_tasks} evidence_weight={prior.evidence_weight:.2f} "
                f"pass={prior.pass_count} "
                f"t2_succ={prior.t2_success_rate:.2f} t3_succ={prior.t3_success_rate:.2f} "
                f"tiers={dict(sorted(prior.tier_turns.items()))} "
                f"median_cost=${prior.median_cost:.4f}"
            )
        for repo, regret in sorted(self._policy_regrets.items()):
            if regret.regret > 0:
                lines.append(
                    f"  regret {repo}: full_avg=${regret.full_avg_cost:.4f} vs "
                    f"baseline_avg=${regret.baseline_avg_cost:.4f} regret={regret.regret:.3f}"
                )
        return lines


def _pick_tier(pick) -> int:
    return parse_tier_label(pick)


def _trace_segment_key(trace: dict) -> str:
    segment = str(trace.get("workflow_segment") or "")
    if segment:
        return segment
    return ""


def _record_weight(record: dict) -> float:
    try:
        weight = float(record.get("_policy_memory_weight", 1.0))
    except (TypeError, ValueError):
        weight = 1.0
    return max(0.0, min(weight, 1.0))


def _weighted_count(records: list[dict]) -> float:
    return sum(_record_weight(record) for record in records)


def _weighted_cost(records: list[dict]) -> float:
    return sum(_record_weight(record) * float(record.get("total_cost") or 0.0) for record in records)


def _trace_tier(trace: dict) -> int:
    tier = trace.get("backend_tier")
    try:
        parsed = int(tier)
    except (TypeError, ValueError):
        parsed = 0
    return max(parsed, parse_tier_label(trace.get("final_backend") or ""))


def _trace_has_value_triggered_escalation(trace: dict) -> bool:
    """Read current trace fields for Value-Triggered Escalation."""
    return bool(
        trace.get("value_triggered_escalation_active")
        or trace.get("value_triggered_escalation_opened")
    )


def _trace_productivity(trace: dict) -> bool | None:
    """Whether this backend turn produced a useful action without infra noise."""
    if trace.get("error_type") or trace.get("parser_error_type"):
        return False
    signals: list[bool | None] = []
    if "action_progress_state" in trace:
        signals.append(_progress_state_productivity(str(trace.get("action_progress_state"))))
    if "progress_state" in trace:
        signals.append(_progress_state_productivity(str(trace.get("progress_state"))))
    if "action_has_progress" in trace:
        signals.append(_optional_trace_bool(trace.get("action_has_progress")))
    if "has_progress" in trace:
        signals.append(_optional_trace_bool(trace.get("has_progress")))
    if True in signals:
        return True
    if any(signal is None for signal in signals):
        return None
    return False if signals else None


def _progress_state_productivity(state: str) -> bool | None:
    if state == "progress":
        return True
    if state == "no_progress":
        return False
    return None


def _optional_trace_bool(value) -> bool | None:
    if value is True:
        return True
    if value is False:
        return False
    return None


def _escalation_action(prior: EscalationPrior) -> tuple[str, int]:
    """Convert Escalation Memory into a next-run Value-Triggered Escalation policy."""
    if prior.attempts <= 0:
        return "default", 3
    if prior.attempts >= 2.0 and prior.resolved == 0 and prior.t3_no_progress_cost >= 0.15:
        return "disable_value_triggered_escalation", 0
    if prior.attempts >= 1.0 and prior.t3_productive_rate < 0.15 and prior.t3_no_progress_cost >= 0.05:
        return "shorten_value_triggered_escalation", 1
    if prior.attempts >= 1.0 and prior.success_rate >= 0.6 and prior.t3_productive_rate >= 0.25:
        return "extend_value_triggered_escalation", 4
    return "default", 3


def _starter_action(prior: StarterPrior, source: str = "") -> tuple[str, int]:
    """Convert Routing Memory into a bounded strongest starter window."""
    if _starter_action_evidence_weight(prior) < 1.0:
        return "default", 0
    if prior.bo_frontload_rate < 0.4:
        return "default", 0
    starter_window_cap: int | None = None
    if (
        prior.budgetflow_starter_attempts >= 2.0
        and prior.budgetflow_starter_failures >= 2.0
        and prior.budgetflow_starter_success_rate < 0.25
        and prior.budgetflow_starter_productive_rate < 0.15
        and prior.budgetflow_starter_no_progress_cost >= 0.15
    ):
        return "default", 0
    if (
        prior.budgetflow_starter_attempts >= 1.0
        and prior.budgetflow_starter_failures >= 1.0
        and prior.budgetflow_starter_success_rate < 0.25
        and prior.budgetflow_starter_productive_rate < 0.15
        and prior.budgetflow_starter_no_progress_cost >= 0.05
    ):
        starter_window_cap = 1
    expensive_success_threshold = 1.0 if source == "task" else 2.0
    if (
        prior.budgetflow_expensive_successes >= expensive_success_threshold
        and prior.bo_frontload_rate >= 0.75
    ):
        return "frontload_strongest", min(4, starter_window_cap or 4)
    if prior.attempts >= 2.0 and prior.bo_frontload_rate >= 0.75:
        return "frontload_strongest", min(3, starter_window_cap or 3)
    return "frontload_strongest", min(2, starter_window_cap or 2)


def _starter_action_evidence_weight(prior: StarterPrior) -> float:
    """Effective starter evidence that can legitimately affect routing."""
    return max(prior.attempts, prior.budgetflow_starter_attempts)
