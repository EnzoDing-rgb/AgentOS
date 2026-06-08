from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class Stage(str, Enum):
    """Compatibility stage labels used by existing harness adapters."""

    LOCALIZATION = "localization"
    REPAIR = "repair"
    VALIDATION = "validation"


@dataclass(frozen=True)
class WorkflowSegment:
    """Coarse workflow state used as a policy signal.

    Default segments are Context, Action, Verification.
    Segment-aware routing means the policy *can* use segment as a feature.
    It does not force model switching.
    """

    name: str  # Context, Action, Verification, or adapter-defined equivalent
    signals: dict[str, float | str | bool] = field(default_factory=dict)

    # Canonical segment names
    CONTEXT = "Context"
    ACTION = "Action"
    VERIFICATION = "Verification"

    @classmethod
    def context(cls, **signals: float | str | bool) -> WorkflowSegment:
        """Gather information, inspect state, form a working hypothesis."""
        return cls(name=cls.CONTEXT, signals=dict(signals))

    @classmethod
    def action(cls, **signals: float | str | bool) -> WorkflowSegment:
        """Make an intervention: edit, write, call a tool, change task state."""
        return cls(name=cls.ACTION, signals=dict(signals))

    @classmethod
    def verification(cls, **signals: float | str | bool) -> WorkflowSegment:
        """Check whether the intervention worked."""
        return cls(name=cls.VERIFICATION, signals=dict(signals))


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ZOMBIE = "zombie"


@dataclass(frozen=True)
class TurnInfo:
    workflow_id: str
    step_index: int
    stage: Stage
    w_i: float
    context_len: int
    signal_source: Literal["explicit", "callback", "proxy", "budget_only"] = "explicit"
    tool_name: str | None = None
    observation_type: str | None = None
    segment: WorkflowSegment | None = None


@dataclass(frozen=True)
class Backend:
    name: str
    tier: int
    cost_per_input_token: float
    cost_per_output_token: float
    rpm_limit: int
    concurrency_limit: int
    mean_output_tokens: int
    progress_score: float
    latency_ms: int


@dataclass(frozen=True)
class CostEstimate:
    expected_cost: float
    reserved_cost: float
    expected_output_tokens: int
    max_output_tokens: int


@dataclass
class LedgerEntry:
    workflow_id: str
    reserved_cost: float = 0.0
    actual_cost: float = 0.0
    current_step: int = 0
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_backend: str | None = None
    last_progress_at: float | None = None
    last_event_at: float | None = None
    active_reservation_id: str | None = None


@dataclass
class BudgetState:
    total_budget: float
    available_budget: float
    reserved_budget: float = 0.0
    spent_budget: float = 0.0


@dataclass(frozen=True)
class GovernorConfig:
    total_budget: float
    default_max_output_tokens: int
    queue_limit: int = 0
    soft_budget: float | None = None
    max_overrun: float = 0.0


@dataclass(frozen=True)
class BackendPressure:
    rpm_used: int
    rpm_limit: int
    concurrency_used: int
    concurrency_limit: int

    @property
    def rpm_ratio(self) -> float:
        if self.rpm_limit == 0:
            return 1.0
        return self.rpm_used / self.rpm_limit

    @property
    def concurrency_ratio(self) -> float:
        if self.concurrency_limit == 0:
            return 1.0
        return self.concurrency_used / self.concurrency_limit


ProgressTable = dict[Stage, dict[str, float]]


@dataclass(frozen=True)
class BackendCallResult:
    backend_name: str
    input_tokens: int
    output_tokens: int
    progress_made: bool
    latency_ms: int
    timed_out: bool = False
    response_text: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens
