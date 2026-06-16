"""Segment-aware adaptive feedback for BudgetFlow routing."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

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
from .failure_classification import is_scoreable
from .learn_policy import LearnPolicyInputs
from .routing_sets import ADAPTIVE_ROUTINGS
from .types import WorkflowSegment

if TYPE_CHECKING:
    from .policy_memory import PolicyMemory

_STAGNATION_EXITS = frozenset(
    {
        "stagnation_no_progress",
        "stagnation_repeat_command",
    }
)


def _is_stagnation(record: dict) -> bool:
    reason = str(record.get("exit_reason") or "")
    if reason in _STAGNATION_EXITS:
        return True
    return reason.startswith("stagnation_")


def _classify_weak_segment(record: dict) -> str:
    if record.get("agent_gold_edited"):
        return WorkflowSegment.ACTION
    if _is_stagnation(record) and not record.get("patch_extracted"):
        return WorkflowSegment.CONTEXT
    return WorkflowSegment.ACTION


@dataclass
class _SegmentBucket:
    weak_count: int = 0
    total: int = 0


@dataclass
class EvidenceRescueState:
    """Open one short high-tier window only after concrete repair evidence.

    This is deliberately not a permanent repair floor. It waits until the
    agent has edited the target/gold file or reached validation, then spends a
    bounded rescue window while there is still budget headroom.
    """

    trigger_turns: int = 6
    window_turns: int = 3
    stop_loss_turns: int = 6
    min_headroom_frac: float = 0.18
    rescue_tier: int = 3
    evidence_turns: int = 0
    window_remaining: int = 0
    window_opened: bool = False

    def forced_min_tier(
        self,
        *,
        segment: str | WorkflowSegment,
        gold_edited: bool,
        current_tier: int,
        remaining_budget: float,
        total_budget: float,
    ) -> int | None:
        segment_name = _segment_name(segment)
        has_evidence = gold_edited and segment_name in (WorkflowSegment.ACTION, WorkflowSegment.VERIFICATION)
        if not has_evidence:
            return None

        self.evidence_turns += 1
        if self.window_remaining > 0:
            self.window_remaining -= 1
            return self.rescue_tier

        if self.window_opened:
            return None

        if self.evidence_turns < self.trigger_turns:
            return None

        if current_tier >= self.rescue_tier:
            return None

        if total_budget <= 0 or (remaining_budget / total_budget) < self.min_headroom_frac:
            return None

        self.window_opened = True
        self.window_remaining = max(0, self.window_turns - 1)
        return self.rescue_tier

    def should_stop_loss(self, *, gold_edited: bool) -> bool:
        if not gold_edited or not self.window_opened or self.window_remaining > 0:
            return False
        return self.evidence_turns >= self.stop_loss_turns


def rescue_state_for_strategy(
    strategy_name: str,
    policy_memory: PolicyMemory | None = None,
    instance_id: str | None = None,
) -> EvidenceRescueState:
    base = EvidenceRescueState()
    if policy_memory is not None and instance_id is not None:
        prior = policy_memory.routing_prior_summary(instance_id, WorkflowSegment.ACTION)
        action = prior.get("learned_action", "default")
        if action == "early_rescue":
            base.trigger_turns = max(2, base.trigger_turns - 3)
            base.window_turns = min(5, base.window_turns + 1)
        elif action == "reduce_rescue":
            base.trigger_turns = min(12, base.trigger_turns + 4)
            base.window_turns = max(1, base.window_turns - 1)
        elif action in {"cap_strongest", "cap_t3"}:
            base.window_turns = max(1, base.window_turns - 1)
            base.stop_loss_turns = max(3, base.stop_loss_turns - 3)
    return base


@dataclass
class AdaptiveRoutingState:
    """Per compare-policy rolling health + in-run recovery knobs."""

    strategy_name: str
    _recent: deque[dict] = field(default_factory=lambda: deque(maxlen=ADAPTIVE_WINDOW))
    _segment_buckets: dict[str, _SegmentBucket] = field(
        default_factory=lambda: {
            WorkflowSegment.CONTEXT: _SegmentBucket(),
            WorkflowSegment.ACTION: _SegmentBucket(),
            WorkflowSegment.VERIFICATION: _SegmentBucket(),
        }
    )
    pressure_boost: float = 0.0
    ttl_steps_remaining: int = 0
    min_tier_floor: int = 1
    last_weak_segment: str | None = None
    rescue: EvidenceRescueState = field(default_factory=EvidenceRescueState)
    policy_memory: object | None = None
    memory_mode: str = "off"
    _current_instance_id: str | None = None
    _prior_summary: dict | None = None
    strongest_starter_action: str = "default"
    strongest_starter_window_remaining: int = 0
    strongest_starter_window_opened: bool = False
    strongest_starter_applied_this_turn: bool = False

    def __post_init__(self) -> None:
        self.rescue = rescue_state_for_strategy(
            self.strategy_name,
            policy_memory=getattr(self, 'policy_memory', None),
            instance_id=getattr(self, '_current_instance_id', None),
        )

    def record_task(self, record: dict) -> None:
        if not is_scoreable(record):
            return
        self._recent.append(record)
        if not record.get("harness_resolved"):
            segment = _classify_weak_segment(record)
            bucket = self._segment_buckets[segment]
            bucket.total += 1
            bucket.weak_count += 1
            self.last_weak_segment = segment
        self._recompute()

    def on_step(self) -> None:
        self.strongest_starter_applied_this_turn = False
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

        0 consecutive fails → cheapest tier (default)
        2+ consecutive fails → second-cheapest tier (skip cheapest)
        Policy "start_second_cheapest" action → second-cheapest regardless of streak
        Starts strongest only when Routing Memory learned that bounded early
        strongest-tier frontload beat delayed BudgetFlow rescue on matched tasks.
        """
        if self.strongest_starter_window_remaining > 0:
            return 3
        action = self._prior_summary.get("learned_action") if self._prior_summary else ""
        if action in {"start_second_cheapest", "start_t2"}:
            return 2
        streak = 0
        for r in reversed(list(self._recent)):
            if r.get("harness_resolved"):
                break
            streak += 1
        if streak >= 2:
            return 2
        return 1

    def set_task_context(self, instance_id: str) -> None:
        """Set current task context and rebuild prior-informed escalation params."""
        self._current_instance_id = instance_id
        if self.policy_memory is not None:
            self._prior_summary = self.policy_memory.routing_prior_summary(
                instance_id, WorkflowSegment.CONTEXT
            )
        self._refresh_strongest_starter_window()
        self.rescue = rescue_state_for_strategy(
            self.strategy_name,
            policy_memory=self.policy_memory,
            instance_id=instance_id,
        )

    def reset_task_runtime(self) -> None:
        self.rescue = rescue_state_for_strategy(
            self.strategy_name,
            policy_memory=self.policy_memory,
            instance_id=self._current_instance_id,
        )
        self._prior_summary = None
        self.strongest_starter_action = "default"
        self.strongest_starter_window_remaining = 0
        self.strongest_starter_window_opened = False
        self.strongest_starter_applied_this_turn = False

    def prior_summary_for_trace(self) -> dict | None:
        return self._prior_summary

    def _refresh_strongest_starter_window(self) -> None:
        prior = self._prior_summary or {}
        action = str(prior.get("strongest_starter_action") or "default")
        if action != "frontload_strongest":
            self.strongest_starter_action = "default"
            self.strongest_starter_window_remaining = 0
            self.strongest_starter_window_opened = False
            self.strongest_starter_applied_this_turn = False
            return
        try:
            window = int(prior.get("strongest_starter_window") or 0)
        except (TypeError, ValueError):
            window = 0
        self.strongest_starter_action = action
        self.strongest_starter_window_remaining = max(0, window)
        self.strongest_starter_window_opened = False
        self.strongest_starter_applied_this_turn = False

    def consume_strongest_starter_tier(self, strongest_tier: int) -> int | None:
        if self.strongest_starter_window_remaining <= 0:
            self.strongest_starter_applied_this_turn = False
            return None
        self.strongest_starter_window_remaining -= 1
        self.strongest_starter_window_opened = True
        self.strongest_starter_applied_this_turn = True
        return strongest_tier

    def status_snippet(self) -> str:
        rescue = (
            f" rescue=evidence:{self.rescue.evidence_turns}"
            f"/window:{self.rescue.window_remaining}"
            if self.rescue.window_opened or self.rescue.evidence_turns
            else ""
        )
        starter = (
            f" starter={self.strongest_starter_action}:{self.strongest_starter_window_remaining}"
            if self.strongest_starter_window_remaining > 0 or self.strongest_starter_window_opened
            else ""
        )
        if self.pressure_boost <= 0 and self.ttl_steps_remaining <= 0:
            if rescue or starter:
                return f"adapt=off{rescue}{starter}"
            return "adapt=off"
        segment = self.last_weak_segment or "-"
        return (
            f"adapt=on boost=+{self.pressure_boost:.2f} "
            f"ttl={self.ttl_steps_remaining} floor_tier={self.min_tier_for_reserve()} "
            f"weak_segment={segment}{rescue}{starter}"
        )

    def _recompute(self) -> None:
        n = len(self._recent)
        if n < ADAPTIVE_MIN_SAMPLES:
            return
        resolved = sum(1 for r in self._recent if r.get("harness_resolved"))
        stagnation = sum(1 for r in self._recent if _is_stagnation(r))
        resolve_rate = resolved / n
        stagnation_frac = stagnation / n

        rep_bucket = self._segment_buckets[WorkflowSegment.ACTION]
        val_bucket = self._segment_buckets[WorkflowSegment.VERIFICATION]
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
        for bucket in self._segment_buckets.values():
            bucket.weak_count = 0
            bucket.total = 0
        self.pressure_boost = 0.0
        self.ttl_steps_remaining = 0
        self.min_tier_floor = 1
        self.last_weak_segment = None
        self.rescue = rescue_state_for_strategy(self.strategy_name)
        for record in records[-ADAPTIVE_WINDOW :]:
            self.record_task(record)


def _segment_name(segment: str | WorkflowSegment) -> str:
    if isinstance(segment, WorkflowSegment):
        return segment.name
    return str(segment or "")


class AdaptiveRoutingRegistry:
    """Thread-safe registry: one adaptive state per active BudgetFlow policy."""

    def __init__(
        self,
        policy_memory: object | None = None,
        memory_mode: str = "off",
        learn_policy_inputs: LearnPolicyInputs | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, AdaptiveRoutingState] = {}
        if learn_policy_inputs is None:
            learn_policy_inputs = (
                LearnPolicyInputs.built_in(
                    routing=policy_memory,
                    escalation=policy_memory,
                    source="policy_memory",
                )
                if policy_memory is not None
                else LearnPolicyInputs.off()
            )
        self._learn_policy_inputs = learn_policy_inputs
        self._policy_memory = policy_memory or learn_policy_inputs.routing
        self._memory_mode = learn_policy_inputs.mode if learn_policy_inputs.routing_enabled else "off"
        if learn_policy_inputs.routing_enabled and memory_mode != "off":
            self._memory_mode = memory_mode

    @property
    def policy_memory(self) -> object | None:
        return self._policy_memory

    @property
    def learn_policy_inputs(self) -> LearnPolicyInputs:
        return self._learn_policy_inputs

    @property
    def memory_mode(self) -> str:
        return self._memory_mode

    def set_policy_memory(self, policy_memory: object) -> None:
        self._policy_memory = policy_memory
        self._learn_policy_inputs = LearnPolicyInputs.built_in(
            routing=policy_memory,
            escalation=policy_memory,
            source="policy_memory",
        )
        self._memory_mode = "built_in"
        with self._lock:
            for state in self._states.values():
                state.policy_memory = policy_memory
                state.memory_mode = self._memory_mode

    def for_strategy(self, strategy_name: str, routing: str) -> AdaptiveRoutingState | None:
        if routing not in ADAPTIVE_ROUTINGS:
            return None
        with self._lock:
            state = self._states.get(strategy_name)
            if state is None:
                state = AdaptiveRoutingState(
                    strategy_name=strategy_name,
                    policy_memory=self._policy_memory,
                    memory_mode=self._memory_mode,
                )
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
            if record.get("routing") not in ADAPTIVE_ROUTINGS:
                continue
            name = record.get("strategy")
            if not name:
                continue
            by_strategy.setdefault(name, []).append(record)
        with self._lock:
            for name, records in by_strategy.items():
                state = AdaptiveRoutingState(
                    strategy_name=name,
                    policy_memory=self._policy_memory,
                    memory_mode=self._memory_mode,
                )
                state.rebuild_from_records(records)
                self._states[name] = state

    def summary_lines(self) -> list[str]:
        with self._lock:
            states = list(self._states.values())
        if not states:
            return []
        lines = ["adaptive_routing (active BudgetFlow policies, always on):"]
        for state in sorted(states, key=lambda s: s.strategy_name):
            lines.append(f"  {state.strategy_name}: {state.status_snippet()}")
        return lines
