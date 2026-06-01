"""Stage-aware adaptive feedback for BudgetFlow routing (always on for budgetflow_full)."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field

from .defaults import (
    ADAPTIVE_MIN_SAMPLES,
    ADAPTIVE_PRESSURE_BOOST,
    ADAPTIVE_PRESSURE_BOOST_STRONG,
    ADAPTIVE_STAGNATION_FRAC,
    ADAPTIVE_TTL_STEPS,
    ADAPTIVE_WEAK_RESOLVE_MAX,
    ADAPTIVE_WINDOW,
    PRESSURE_MAX,
)
from .types import Stage

_STAGNATION_EXITS = frozenset(
    {
        "stagnation_no_progress",
        "stagnation_repeat_command",
        "stagnation_no_progress_worktree_patch",
        "stagnation_repeat_command_worktree_patch",
    }
)


def _is_stagnation(record: dict) -> bool:
    reason = str(record.get("exit_reason") or "")
    if reason in _STAGNATION_EXITS:
        return True
    return reason.startswith("stagnation_")


def _infer_weak_stage(record: dict) -> Stage:
    if record.get("agent_gold_edited"):
        return Stage.REPAIR
    if _is_stagnation(record) and not record.get("patch_extracted"):
        return Stage.LOCALIZATION
    return Stage.REPAIR


@dataclass
class _StageBucket:
    weak_count: int = 0
    total: int = 0


@dataclass
class AdaptiveRoutingState:
    """Per compare-policy rolling health + in-run recovery knobs."""

    strategy_name: str
    _recent: deque[dict] = field(default_factory=lambda: deque(maxlen=ADAPTIVE_WINDOW))
    _stage_buckets: dict[Stage, _StageBucket] = field(
        default_factory=lambda: {
            Stage.LOCALIZATION: _StageBucket(),
            Stage.REPAIR: _StageBucket(),
            Stage.VALIDATION: _StageBucket(),
        }
    )
    pressure_boost: float = 0.0
    ttl_steps_remaining: int = 0
    min_tier_floor: int = 1
    last_weak_stage: Stage | None = None

    def record_task(self, record: dict) -> None:
        self._recent.append(record)
        if not record.get("harness_resolved"):
            stage = _infer_weak_stage(record)
            bucket = self._stage_buckets[stage]
            bucket.total += 1
            bucket.weak_count += 1
            self.last_weak_stage = stage
        self._recompute()

    def on_step(self) -> None:
        if self.ttl_steps_remaining > 0:
            self.ttl_steps_remaining -= 1
        if self.ttl_steps_remaining <= 0 and self.pressure_boost <= 0.0:
            self.min_tier_floor = 1

    def effective_pressure(self, base_pressure: float) -> float:
        return min(PRESSURE_MAX, base_pressure + self.pressure_boost)

    def min_tier_for_reserve(self) -> int:
        if self.ttl_steps_remaining > 0:
            return max(self.min_tier_floor, 2)
        return 1

    def starting_tier(self) -> int:
        """Recommended tier to start the next task, based on recent outcomes.

        0 consecutive fails → T1 (default)
        2+ consecutive fails → T2 (skip cheapest)
        4+ consecutive fails → T3 (serious trouble, start strong)
        A resolved task resets the streak to 0.
        """
        streak = 0
        for r in reversed(list(self._recent)):
            if r.get("harness_resolved"):
                break
            streak += 1
        if streak >= 4:
            return 3
        if streak >= 2:
            return 2
        return 1

    def status_snippet(self) -> str:
        if self.pressure_boost <= 0 and self.ttl_steps_remaining <= 0:
            return "adapt=off"
        stage = self.last_weak_stage.value if self.last_weak_stage else "-"
        return (
            f"adapt=on boost=+{self.pressure_boost:.2f} "
            f"ttl={self.ttl_steps_remaining} floor_tier={self.min_tier_for_reserve()} "
            f"weak_stage={stage}"
        )

    def _recompute(self) -> None:
        n = len(self._recent)
        if n < ADAPTIVE_MIN_SAMPLES:
            return
        resolved = sum(1 for r in self._recent if r.get("harness_resolved"))
        stagnation = sum(1 for r in self._recent if _is_stagnation(r))
        resolve_rate = resolved / n
        stagnation_frac = stagnation / n

        rep_bucket = self._stage_buckets[Stage.REPAIR]
        val_bucket = self._stage_buckets[Stage.VALIDATION]
        rep_weak = rep_bucket.weak_count >= 2
        val_weak = val_bucket.weak_count >= 2

        weak = (
            resolve_rate <= ADAPTIVE_WEAK_RESOLVE_MAX
            or stagnation_frac >= ADAPTIVE_STAGNATION_FRAC
            or rep_weak
            or val_weak
        )
        if not weak:
            self.pressure_boost = 0.0
            self.ttl_steps_remaining = 0
            self.min_tier_floor = 1
            return

        # When stagnation dominates, boosting pressure makes upgrades HARDER,
        # which keeps the agent on cheap models → more stagnation → death spiral.
        # Instead, keep pressure neutral and rely on min_tier_floor to prevent T1.
        dominated_by_stagnation = stagnation_frac >= ADAPTIVE_STAGNATION_FRAC
        if dominated_by_stagnation:
            self.pressure_boost = 0.0
        else:
            boost = ADAPTIVE_PRESSURE_BOOST
            if resolve_rate == 0 or rep_weak or val_weak:
                boost = ADAPTIVE_PRESSURE_BOOST_STRONG
            self.pressure_boost = min(PRESSURE_MAX * 0.85, max(self.pressure_boost, boost))
        self.ttl_steps_remaining = max(self.ttl_steps_remaining, ADAPTIVE_TTL_STEPS)
        self.min_tier_floor = 2

    def rebuild_from_records(self, records: list[dict]) -> None:
        self._recent.clear()
        for bucket in self._stage_buckets.values():
            bucket.weak_count = 0
            bucket.total = 0
        self.pressure_boost = 0.0
        self.ttl_steps_remaining = 0
        self.min_tier_floor = 1
        self.last_weak_stage = None
        for record in records[-ADAPTIVE_WINDOW :]:
            self.record_task(record)


class AdaptiveRoutingRegistry:
    """Thread-safe registry: one adaptive state per budgetflow_full compare policy."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, AdaptiveRoutingState] = {}

    def for_strategy(self, strategy_name: str, routing: str) -> AdaptiveRoutingState | None:
        if routing not in ("budgetflow_full", "stage_blind"):
            return None
        with self._lock:
            state = self._states.get(strategy_name)
            if state is None:
                state = AdaptiveRoutingState(strategy_name=strategy_name)
                self._states[strategy_name] = state
            return state

    def record_task(self, strategy_name: str, routing: str, record: dict) -> None:
        state = self.for_strategy(strategy_name, routing)
        if state is not None:
            state.record_task(record)

    def rebuild_from_jsonl(self, path) -> None:
        import json

        if not path.is_file():
            return
        by_strategy: dict[str, list[dict]] = {}
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("routing") not in ("budgetflow_full", "stage_blind"):
                continue
            name = record.get("strategy")
            if not name:
                continue
            by_strategy.setdefault(name, []).append(record)
        with self._lock:
            for name, records in by_strategy.items():
                state = AdaptiveRoutingState(strategy_name=name)
                state.rebuild_from_records(records)
                self._states[name] = state

    def summary_lines(self) -> list[str]:
        with self._lock:
            states = list(self._states.values())
        if not states:
            return []
        lines = ["adaptive_routing (budgetflow_full, always on):"]
        for state in sorted(states, key=lambda s: s.strategy_name):
            lines.append(f"  {state.strategy_name}: {state.status_snippet()}")
        return lines

