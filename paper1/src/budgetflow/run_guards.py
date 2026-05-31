"""Compare-run health guards: detect pipeline/upstream failure and stop burning budget."""

from __future__ import annotations

import re
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .console_log import tag

# Defaults tuned for 15×7 (105 runs); override via CompareRunGuards config.
GLOBAL_WINDOW = 15
GLOBAL_MIN_SAMPLES = 10
# Legacy name kept for CompareRunGuards field; global halt uses resolved count only.
GLOBAL_PATCH_RATE_MIN = 0.20
POLICY_CONSECUTIVE_FAIL = 5
POLICY_PIPELINE_FAIL_MIN = 4
UPSTREAM_CONSECUTIVE = 8

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

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _recent: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=GLOBAL_WINDOW), repr=False)
    _strategy_streak: dict[str, int] = field(default_factory=dict, repr=False)
    _halted_strategies: set[str] = field(default_factory=set, repr=False)
    _abort_all_reason: str | None = field(default=None, repr=False)
    _upstream_streak: int = field(default=0, repr=False)

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
                resolved_n = sum(1 for r in window if r.get("harness_resolved"))
                patch_n = sum(1 for r in window if r.get("patch_extracted"))
                if resolved_n == 0:
                    patch_rate = patch_n / len(window)
                    self._abort_all_reason = (
                        f"global_guard last={len(window)} resolved=0 patch_extracted={patch_n} "
                        f"patch_rate={patch_rate:.0%} (agent/harness not producing passes)"
                    )
                    return GuardAction(halt_all=True, reason=self._abort_all_reason)

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
    if record.get("harness_resolved"):
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


def _looks_upstream(message: str) -> bool:
    text = message or ""
    return any(p.search(text) for p in _UPSTREAM_PATTERNS)
