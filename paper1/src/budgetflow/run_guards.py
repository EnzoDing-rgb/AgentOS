"""Compare-run health guards: detect pipeline/upstream failure and stop burning budget."""

from __future__ import annotations

import re
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .console_log import tag
from .failure_classification import is_score_abort, is_score_pass, is_score_true_fail
from .harness_contamination import host_dependency_contamination_requires_global_halt
from .model_tiers import MODEL_CATALOG, parse_tier_label

# Defaults tuned for 15×7 (105 runs); override via CompareRunGuards config.
GLOBAL_WINDOW = 200
GLOBAL_MIN_SAMPLES = 200
# Legacy name kept for CompareRunGuards field; global halt uses resolved count only.
GLOBAL_PATCH_RATE_MIN = 0.20
POLICY_CONSECUTIVE_FAIL = 8
POLICY_PIPELINE_FAIL_MIN = 6
UPSTREAM_CONSECUTIVE = 100
TASK_LEVEL_TIER_MIX_MIN_ROWS = 5

_PIPELINE_EXIT_REASONS = frozenset(
    {
        "stagnation_no_progress",
        "stagnation_repeat_command",
    }
)

_UPSTREAM_PATTERNS = (
    re.compile(r"chatgpt account", re.I),
    re.compile(r"invalid_request", re.I),
    re.compile(r"model is not supported", re.I),
    re.compile(r"service temporarily unavailable", re.I),
    re.compile(r"\b503\b"),
    re.compile(r"upstream_error", re.I),
    re.compile(r"badrequesterror", re.I),
    re.compile(r"llm provider not provided", re.I),
)

# Patterns that indicate payment/billing issues — halt immediately, don't retry.
_FATAL_BILLING_PATTERNS = (
    re.compile(r"overdue.payment", re.I),
    re.compile(r"Access denied, please make sure your account is in good standing", re.I),
    re.compile(r"insufficient.balance", re.I),
    re.compile(r"account.*arrears", re.I),
    re.compile(r"billing.*issue", re.I),
)


@dataclass(frozen=True)
class GuardAction:
    halt_all: bool = False
    halt_strategy: str | None = None
    reason: str = ""

    @property
    def should_stop_batch(self) -> bool:
        return self.halt_all or bool(self.halt_strategy)


@dataclass
class CompareRunGuards:
    """Thread-safe guards shared across parallel policy batches."""

    global_window: int = GLOBAL_WINDOW
    global_min_samples: int = GLOBAL_MIN_SAMPLES
    global_patch_rate_min: float = GLOBAL_PATCH_RATE_MIN
    policy_consecutive_fail: int = POLICY_CONSECUTIVE_FAIL
    policy_pipeline_fail_min: int = POLICY_PIPELINE_FAIL_MIN
    upstream_consecutive: int = UPSTREAM_CONSECUTIVE
    task_level_tier_mix_min_rows: int = TASK_LEVEL_TIER_MIX_MIN_ROWS

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _recent: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=GLOBAL_WINDOW), repr=False)
    _strategy_streak: dict[str, int] = field(default_factory=dict, repr=False)
    _halted_strategies: set[str] = field(default_factory=set, repr=False)
    _abort_all_reason: str | None = field(default=None, repr=False)
    _upstream_streak: int = field(default=0, repr=False)
    _task_level_rows: int = field(default=0, repr=False)
    _task_level_strongest_rows: int = field(default=0, repr=False)
    _task_level_single_tier: int | None = field(default=None, repr=False)

    def is_aborted(self) -> bool:
        with self._lock:
            return self._abort_all_reason is not None

    def abort_reason(self) -> str | None:
        with self._lock:
            return self._abort_all_reason

    def is_strategy_halted(self, strategy: str) -> bool:
        with self._lock:
            return strategy in self._halted_strategies or self._abort_all_reason is not None

    def record_task(self, record: dict[str, Any]) -> GuardAction:
        with self._lock:
            if self._abort_all_reason:
                return GuardAction(halt_all=True, reason=self._abort_all_reason)

            strategy = str(record.get("strategy") or "")
            self._recent.append(record)

            if host_dependency_contamination_requires_global_halt(str(record.get("detail") or "")):
                self._abort_all_reason = (
                    f"host_dependency_contamination strategy={strategy} "
                    f"task={record.get('instance_id') or ''}"
                )
                return GuardAction(halt_all=True, reason=self._abort_all_reason)

            action = self._record_task_level_tier_mix(record)
            if action.should_stop_batch:
                return action

            if _is_pipeline_failure(record):
                self._strategy_streak[strategy] = self._strategy_streak.get(strategy, 0) + 1
            else:
                self._strategy_streak[strategy] = 0

            streak = self._strategy_streak.get(strategy, 0)
            if streak >= self.policy_consecutive_fail:
                pipeline_n = sum(1 for r in self._recent if r.get("strategy") == strategy and _is_pipeline_failure(r))
                if pipeline_n >= self.policy_pipeline_fail_min:
                    self._halted_strategies.add(strategy)
                    reason = (
                        f"policy_guard strategy={strategy} consecutive_fail={streak} "
                        f"(pipeline exits: no patch / stagnation)"
                    )
                    return GuardAction(halt_strategy=strategy, reason=reason)

            if len(self._recent) >= self.global_min_samples:
                window = list(self._recent)
                scoreable = [r for r in window if not is_score_abort(r)]
                resolved_n = sum(1 for r in scoreable if is_score_pass(r))
                patch_n = sum(1 for r in scoreable if r.get("patch_extracted"))
                if resolved_n == 0:
                    patch_rate = patch_n / max(len(scoreable), 1)
                    self._abort_all_reason = (
                        f"global_guard last={len(window)} scoreable={len(scoreable)} "
                        f"resolved=0 patch_extracted={patch_n} "
                        f"patch_rate={patch_rate:.0%} (agent/harness not producing passes)"
                    )
                    return GuardAction(halt_all=True, reason=self._abort_all_reason)

            return GuardAction()

    def _record_task_level_tier_mix(self, record: dict[str, Any]) -> GuardAction:
        """Abort when task-level BudgetFlow silently degenerates into a fixed tier.

        ``budgetflow_task_level`` is a routing policy, not another fixed-tier
        baseline. If all completed rows use the same tier after a few tasks, the
        run is no longer testing the intended mechanism.
        """
        if str(record.get("strategy") or "") != "budgetflow_task_level":
            return GuardAction()
        if is_score_abort(record):
            return GuardAction()

        strongest_tier = max((cfg.tier for cfg in MODEL_CATALOG.configs), default=0)
        if strongest_tier <= 0:
            return GuardAction()
        tiers = {
            parse_tier_label(pick)
            for pick in (record.get("backend_picks") or [])
            if parse_tier_label(pick) > 0
        }
        if not tiers:
            return GuardAction()

        self._task_level_rows += 1
        if strongest_tier in tiers:
            self._task_level_strongest_rows += 1
        record_single_tier = next(iter(tiers)) if len(tiers) == 1 else None
        if self._task_level_single_tier is None:
            self._task_level_single_tier = record_single_tier
        elif self._task_level_single_tier != record_single_tier:
            self._task_level_single_tier = 0
        if (
            self._task_level_rows >= self.task_level_tier_mix_min_rows
            and self._task_level_single_tier
        ):
            if _task_level_frontier_selection_explained(record):
                return GuardAction()
            fixed_tier = self._task_level_single_tier
            reason = (
                "mechanism_guard strategy=budgetflow_task_level "
                f"rows={self._task_level_rows} fixed_tier=T{fixed_tier}; "
                "task-level routing degenerated into a fixed-tier run"
            )
            self._halted_strategies.add("budgetflow_task_level")
            return GuardAction(halt_strategy="budgetflow_task_level", reason=reason)
        return GuardAction()

    def record_upstream_error(self, message: str, *, backend: str) -> GuardAction:
        if not _looks_upstream(message):
            with self._lock:
                self._upstream_streak = 0
            return GuardAction()

        with self._lock:
            if self._abort_all_reason:
                return GuardAction(halt_all=True, reason=self._abort_all_reason)

            self._upstream_streak += 1
            if self._upstream_streak >= self.upstream_consecutive:
                self._abort_all_reason = (
                    f"upstream_guard consecutive={self._upstream_streak} backend={backend} "
                    f"sample={message[:120]}"
                )
                return GuardAction(halt_all=True, reason=self._abort_all_reason)
            return GuardAction()

    def log_action(self, action: GuardAction) -> None:
        if not action.reason:
            return
        if action.halt_all:
            print(f"{tag('guard', bold=False)} HALT_ALL {action.reason}", flush=True)
        elif action.halt_strategy:
            print(
                f"{tag('guard', bold=False)} HALT_STRATEGY {action.halt_strategy} {action.reason}",
                flush=True,
            )


_active_guard: CompareRunGuards | None = None
_guard_lock = threading.Lock()


def set_active_guard(guard: CompareRunGuards | None) -> None:
    global _active_guard
    with _guard_lock:
        _active_guard = guard


def get_active_guard() -> CompareRunGuards | None:
    with _guard_lock:
        return _active_guard


def record_upstream_error(message: str, *, backend: str) -> GuardAction:
    guard = get_active_guard()
    if guard is None:
        return GuardAction()
    action = guard.record_upstream_error(message, backend=backend)
    guard.log_action(action)
    return action


def _is_pipeline_failure(record: dict[str, Any]) -> bool:
    if is_score_abort(record):
        return False
    if is_score_pass(record):
        return False
    if not is_score_true_fail(record):
        return False
    if not record.get("patch_extracted"):
        return True
    reason = str(record.get("exit_reason") or "")
    status = str(record.get("exit_status") or "")
    if reason in _PIPELINE_EXIT_REASONS:
        return True
    if status == "StagnationExit":
        return True
    return False


def _task_level_frontier_selection_explained(record: dict[str, Any]) -> bool:
    """Return True when fixed-tier use is an explicit frontier decision."""
    for trace in record.get("turn_traces") or []:
        if not isinstance(trace, dict):
            continue
        reason = str(trace.get("router_reason") or "")
        if reason in {
            "bf_task_start_marginal_yield_t3",
            "bf_task_start_critical_value_probe",
            "bf_task_start_uncertain_frontier_probe",
            "bf_task_start_reference_frontier",
        }:
            return True
        policy = trace.get("policy_decision")
        if not isinstance(policy, dict):
            continue
        policy_reason = str(policy.get("reason") or "")
        if policy_reason in {
            "critical_value_probe",
            "task_level_fixed_task_start",
            "task_level_critical_value_probe",
            "task_level_uncertain_frontier_probe",
            "task_level_reference_frontier",
        }:
            return True
        scores = policy.get("scores")
        if isinstance(scores, dict) and float(scores.get("paid_upgrade_candidate") or 0.0) > 0:
            return True
        if isinstance(scores, dict) and float(scores.get("reference_frontier_candidate") or 0.0) > 0:
            return True
    return False


def _looks_upstream(message: str) -> bool:
    text = message or ""
    return any(p.search(text) for p in _UPSTREAM_PATTERNS)


def is_fatal_billing_error(message: str) -> bool:
    """Check if error is a payment/billing issue that should halt immediately."""
    text = message or ""
    return any(p.search(text) for p in _FATAL_BILLING_PATTERNS)


def record_billing_halt(message: str, *, backend: str) -> GuardAction:
    """Create an immediate halt-all action for billing errors."""
    reason = f"billing_guard backend={backend} sample={message[:120]}"
    guard = get_active_guard()
    if guard is not None:
        with guard._lock:
            guard._abort_all_reason = reason
    return GuardAction(halt_all=True, reason=reason)
