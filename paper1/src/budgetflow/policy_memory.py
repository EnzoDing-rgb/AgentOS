"""PolicyMemory / RoutingPrior — heuristic statistical learning from historical JSONL.

No ML/RL. Rolling window, EWMA, success_rate, median_cost, failure_count.
Rebuilds on resume; writes routing_prior_summary into every routing trace.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .defaults import POLICY_REGRET_THRESHOLD
from .model_tiers import parse_tier_label
from .types import Stage


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
    pass_count: int = 0
    tier_turns: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    tier_success_rate: dict[int, float] = field(default_factory=dict)
    median_cost: float = 0.0
    failure_classes: Counter = field(default_factory=Counter)
    stage_tier_success: dict[str, dict[int, float]] = field(default_factory=lambda: defaultdict(dict))

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
    def t2_stage_success(self) -> dict[str, float]:
        return {stage: by_tier.get(2, 0.0) for stage, by_tier in self.stage_tier_success.items()}

    @property
    def t3_stage_success(self) -> dict[str, float]:
        return {stage: by_tier.get(3, 0.0) for stage, by_tier in self.stage_tier_success.items()}


@dataclass
class TaskPrior:
    instance_id: str
    repo: str = ""
    seen: int = 0
    pass_count: int = 0
    median_cost: float = 0.0
    all_pro_failures: int = 0
    tier_turns: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    failure_classes: Counter = field(default_factory=Counter)

    def __post_init__(self) -> None:
        if not self.repo:
            self.repo = _extract_repo(self.instance_id)


@dataclass
class PolicyRegret:
    repo: str
    full_cost: float = 0.0
    tight_cost: float = 0.0
    full_pass: int = 0
    tight_pass: int = 0
    full_count: int = 0
    tight_count: int = 0
    regret: float = 0.0  # positive = full more expensive without more passes

    @property
    def full_avg_cost(self) -> float:
        return self.full_cost / max(self.full_count, 1)

    @property
    def tight_avg_cost(self) -> float:
        return self.tight_cost / max(self.tight_count, 1)


class PolicyMemory:
    """Heuristic prior store rebuilt from JSONL outcomes.

    Consumes verified task records (harness_resolved, total_cost, turn_traces,
    failure_class, backend_picks).  Zero ML/RL — just rolling window stats,
    EWMA, counters, and medians.
    """

    def __init__(self, ewma_alpha: float = 0.3, window_size: int = 20, regret_threshold: float | None = None):
        self._ewma_alpha = ewma_alpha
        self._window_size = window_size
        self.regret_threshold = regret_threshold if regret_threshold is not None else POLICY_REGRET_THRESHOLD
        self._repo_priors: dict[str, RepoPrior] = {}
        self._task_priors: dict[str, TaskPrior] = {}
        self._policy_regrets: dict[str, PolicyRegret] = {}
        self._record_count: int = 0
        self._source_path: str = ""

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
        """Rebuild all priors from a list of outcome records."""
        self._repo_priors.clear()
        self._task_priors.clear()
        self._policy_regrets.clear()
        self._record_count = len(records)

        # Group by repo
        repo_records: dict[str, list[dict]] = defaultdict(list)
        task_records: dict[str, list[dict]] = defaultdict(list)
        for r in records:
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

    def _build_repo_prior(self, repo: str, records: list[dict]) -> RepoPrior:
        prior = RepoPrior(repo=repo)
        prior.total_tasks = len({r.get("instance_id") for r in records})
        prior.pass_count = sum(1 for r in records if r.get("harness_resolved"))

        costs = sorted(float(r.get("total_cost") or 0) for r in records)
        if costs:
            mid = len(costs) // 2
            prior.median_cost = costs[mid] if len(costs) % 2 else (costs[mid - 1] + costs[mid]) / 2

        tier_pass: dict[int, int] = defaultdict(int)
        tier_total: dict[int, int] = defaultdict(int)
        stage_tier_pass: dict[str, dict[int, list[bool]]] = defaultdict(lambda: defaultdict(list))

        for r in records:
            picks = r.get("backend_picks") or []
            tiers_seen: set[int] = set()
            for pick in picks:
                tier = _pick_tier(pick)
                if tier > 0:
                    prior.tier_turns[tier] += 1
                    tiers_seen.add(tier)
            passed = bool(r.get("harness_resolved"))
            for tier in tiers_seen:
                tier_total[tier] += 1
                tier_pass[tier] += 1 if passed else 0

            prior.failure_classes[str(r.get("failure_class") or "unknown")] += 1

            # Stage-level priors from turn_traces
            traces = r.get("turn_traces") or []
            stages_by_tier: dict[int, set[Stage]] = defaultdict(set)
            for t in traces:
                stage_str = str(t.get("stage") or "").lower()
                tier = t.get("backend_tier")
                try:
                    stage = Stage(stage_str)
                except ValueError:
                    continue
                try:
                    tier_int = int(tier)
                except (TypeError, ValueError):
                    continue
                if tier_int > 0:
                    stages_by_tier[tier_int].add(stage)
            for tier, stages in stages_by_tier.items():
                for stage in stages:
                    stage_tier_pass[stage.value][tier].append(passed)

        prior.tier_success_rate = {
            tier: tier_pass[tier] / max(tier_total[tier], 1)
            for tier in sorted(tier_total)
        }
        prior.stage_tier_success = defaultdict(dict)
        for stage, by_tier in stage_tier_pass.items():
            prior.stage_tier_success[stage] = {
                tier: sum(values) / max(len(values), 1)
                for tier, values in sorted(by_tier.items())
            }
        return prior

    def _build_task_prior(self, instance_id: str, records: list[dict]) -> TaskPrior:
        prior = TaskPrior(instance_id=instance_id)
        prior.seen = len(records)
        prior.pass_count = sum(1 for r in records if r.get("harness_resolved"))

        costs = sorted(float(r.get("total_cost") or 0) for r in records)
        if costs:
            mid = len(costs) // 2
            prior.median_cost = costs[mid] if len(costs) % 2 else (costs[mid - 1] + costs[mid]) / 2

        for r in records:
            prior.failure_classes[str(r.get("failure_class") or "unknown")] += 1
            if r.get("strategy") == "all_pro":
                if not r.get("harness_resolved"):
                    prior.all_pro_failures += 1
            picks = r.get("backend_picks") or []
            for p in picks:
                tier = _pick_tier(p)
                if tier > 0:
                    prior.tier_turns[tier] += 1
        return prior

    def _build_policy_regret(self, repo: str, records: list[dict]) -> PolicyRegret:
        regret = PolicyRegret(repo=repo)
        # Group by instance_id to compare full vs tight
        by_task: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
        for r in records:
            iid = str(r.get("instance_id") or "")
            routing = str(r.get("routing") or "")
            if routing in ("budgetflow_full", "budgetflow_conservative", "budgetflow_value_aware") or "budgetflow_full" in routing:
                by_task[iid]["full"].append(r)
            elif "budget_only" in routing:
                by_task[iid]["tight"].append(r)

        for iid, groups in by_task.items():
            full_recs = groups.get("full", [])
            tight_recs = groups.get("tight", [])
            if not full_recs or not tight_recs:
                continue
            regret.full_count += len(full_recs)
            regret.tight_count += len(tight_recs)
            regret.full_cost += sum(float(r.get("total_cost") or 0) for r in full_recs)
            regret.tight_cost += sum(float(r.get("total_cost") or 0) for r in tight_recs)
            regret.full_pass += sum(1 for r in full_recs if r.get("harness_resolved"))
            regret.tight_pass += sum(1 for r in tight_recs if r.get("harness_resolved"))

        if regret.tight_count > 0 and regret.full_count > 0:
            full_avg = regret.full_avg_cost
            tight_avg = regret.tight_avg_cost
            full_rate = regret.full_pass / max(regret.full_count, 1)
            tight_rate = regret.tight_pass / max(regret.tight_count, 1)
            if full_rate <= tight_rate and full_avg > tight_avg:
                regret.regret = full_avg - tight_avg
            elif full_avg > tight_avg * 1.3:
                regret.regret = (full_avg - tight_avg) / tight_avg
        return regret

    # ── query ──────────────────────────────────────────────────────────────

    def repo_prior(self, instance_id: str) -> RepoPrior:
        repo = _extract_repo(instance_id)
        return self._repo_priors.get(repo, RepoPrior(repo=repo))

    def task_prior(self, instance_id: str) -> TaskPrior:
        return self._task_priors.get(instance_id, TaskPrior(instance_id=instance_id))

    def policy_regret(self, instance_id: str) -> PolicyRegret | None:
        repo = _extract_repo(instance_id)
        return self._policy_regrets.get(repo)

    def routing_prior_summary(self, instance_id: str, stage: Stage | None = None) -> dict:
        repo = self.repo_prior(instance_id)
        task = self.task_prior(instance_id)
        regret = self.policy_regret(instance_id)

        # Determine learned action
        action = self._learned_action(instance_id, stage)

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
            "repo_median_cost": round(repo.median_cost, 4),
            "task_seen": task.seen,
            "task_pass_count": task.pass_count,
            "task_median_cost": round(task.median_cost, 4),
            "task_all_pro_failures": task.all_pro_failures,
            "recent_failure_axis": task_top_failure,
            "full_vs_tight_regret": round(regret.regret if regret else 0, 3),
            "learned_action": action,
            "regret_threshold": self.regret_threshold,
            "policy_memory_source": self._source_path or "",
        }
        if stage:
            summary["stage_t2_success"] = round(repo.t2_stage_success.get(stage.value, 0), 3)
            summary["stage_t3_success"] = round(repo.t3_stage_success.get(stage.value, 0), 3)
            summary["stage_tier_success"] = {
                str(k): round(v, 3)
                for k, v in sorted(repo.stage_tier_success.get(stage.value, {}).items())
            }
        return summary

    def _learned_action(self, instance_id: str, stage: Stage | None) -> str:
        repo = self.repo_prior(instance_id)
        task = self.task_prior(instance_id)
        regret = self.policy_regret(instance_id)

        # Rule 5: extract_fail/format_error → protocol issue
        top_failures = [k for k, _ in task.failure_classes.most_common(3) if k != "pass"]
        protocol_fails = {"extract_fail", "format_error", "parser_fail"}
        if any(f in protocol_fails for f in top_failures):
            return "protocol_issue"

        # Rule 4: all_pro repeated failures → reduce rescue
        if task.all_pro_failures >= 2:
            return "reduce_rescue"

        # Rule 3: full vs tight regret → cap strongest-tier rescue
        if regret and regret.regret > self.regret_threshold and regret.full_count >= 2:
            return "cap_strongest"

        repair_key = Stage.REPAIR.value
        loc_key = Stage.LOCALIZATION.value

        # Rule 1: second-tier repair success low → early strongest-tier rescue
        if stage == Stage.REPAIR or stage is None:
            t2_repair = repo.t2_stage_success.get(repair_key, 0)
            if t2_repair < 0.35 and repo.total_tasks >= 3:
                return "early_rescue"

        # Rule 2: second-tier localization good → skip cheapest on start
        if stage == Stage.LOCALIZATION:
            t2_loc = repo.t2_stage_success.get(loc_key, 0)
            if t2_loc > 0.55:
                return "start_second_cheapest"

        return "default"

    # ── write-through ──────────────────────────────────────────────────────

    def record_outcome(self, record: dict) -> None:
        """Incrementally update priors after a single task completes."""
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
        passed = bool(record.get("harness_resolved"))
        prior.pass_count = old.pass_count + (1 if passed else 0)
        new_cost = float(record.get("total_cost") or 0)
        prior.median_cost = a * new_cost + (1 - a) * old.median_cost
        prior.all_pro_failures = old.all_pro_failures + (
            1 if record.get("strategy") == "all_pro" and not passed else 0
        )
        prior.tier_turns = defaultdict(int, old.tier_turns)
        for p in record.get("backend_picks") or []:
            tier = _pick_tier(p)
            if tier > 0:
                prior.tier_turns[tier] += 1
        prior.failure_classes = Counter(old.failure_classes)
        prior.failure_classes[str(record.get("failure_class") or "unknown")] += 1
        return prior

    # ── summary ────────────────────────────────────────────────────────────

    def summary_lines(self) -> list[str]:
        lines = ["policy_memory:"]
        lines.append(f"  records={self._record_count} repos={len(self._repo_priors)} tasks={len(self._task_priors)}")
        for repo, prior in sorted(self._repo_priors.items()):
            lines.append(
                f"  {repo}: tasks={prior.total_tasks} pass={prior.pass_count} "
                f"t2_succ={prior.t2_success_rate:.2f} t3_succ={prior.t3_success_rate:.2f} "
                f"tiers={dict(sorted(prior.tier_turns.items()))} "
                f"median_cost=${prior.median_cost:.4f}"
            )
        for repo, regret in sorted(self._policy_regrets.items()):
            if regret.regret > 0:
                lines.append(
                    f"  regret {repo}: full_avg=${regret.full_avg_cost:.4f} vs "
                    f"tight_avg=${regret.tight_avg_cost:.4f} regret={regret.regret:.3f}"
                )
        return lines


def _pick_tier(pick) -> int:
    return parse_tier_label(pick)
