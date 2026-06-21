from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .budget_pressure import live_budget_pressure
from .governor import BudgetGovernor
from .ledger import WorkflowLedgerStore
from .mock_backend import MockBackend, STAGE_OUTPUT_MULTIPLIER
from .scheduler import SchedulerDecision, WorkflowScheduler
from .selector import BudgetFlowSelector, SelectionDecision
from .types import Backend, BackendCallResult, ProgressTable, Stage, TurnInfo, WorkflowStatus
from .zombie import ZombieDetector


@dataclass(frozen=True)
class WorkflowStep:
    stage: Stage
    input_tokens: int
    w_i: float


@dataclass(frozen=True)
class WorkflowSpec:
    workflow_id: str
    steps: tuple[WorkflowStep, ...]


@dataclass(frozen=True)
class StepTrace:
    workflow_id: str
    step_index: int
    stage: Stage
    chosen_backend: str
    scheduler_decision: str
    progress_made: bool
    actual_cost: float
    status: str
    response_text: str = ""


@dataclass(frozen=True)
class WorkflowResult:
    workflow_id: str
    resolved: bool
    total_cost: float
    traces: tuple[StepTrace, ...]


class MinimalAgentLoop:
    def __init__(
        self,
        backends: list[Backend],
        governor: BudgetGovernor,
        ledger: WorkflowLedgerStore,
        selector: BudgetFlowSelector,
        scheduler: WorkflowScheduler,
        zombie_detector: ZombieDetector,
        budget_pressure: float,
        backend_picker: Callable[[TurnInfo, list[Backend], BudgetFlowSelector, float, dict[str, float]], Backend] | None = None,
        backend_runner: Callable[[Backend, TurnInfo, int], BackendCallResult] | None = None,
    ) -> None:
        self.backends = sorted(backends, key=lambda backend: backend.tier)
        self.governor = governor
        self.ledger = ledger
        self.selector = selector
        self.scheduler = scheduler
        self.zombie_detector = zombie_detector
        self._pressure_init = budget_pressure
        self.budget_pressure = budget_pressure
        self.mock_backends = {backend.name: MockBackend(backend) for backend in self.backends}
        self.backend_picker = backend_picker
        self.backend_runner = backend_runner

    def run_workflow(self, spec: WorkflowSpec) -> WorkflowResult:
        traces: list[StepTrace] = []
        completed_steps = 0

        for step_index, step in enumerate(spec.steps, start=1):
            turn = TurnInfo(
                workflow_id=spec.workflow_id,
                step_index=step_index,
                stage=step.stage,
                w_i=step.w_i,
                context_len=step.input_tokens,
            )
            result = self._run_step(turn, step.input_tokens)
            traces.append(result)
            if result.status != WorkflowStatus.COMPLETED.value:
                break
            if result.progress_made:
                completed_steps += 1

        resolved = completed_steps == len(spec.steps)
        total_cost = sum(trace.actual_cost for trace in traces)
        return WorkflowResult(
            workflow_id=spec.workflow_id,
            resolved=resolved,
            total_cost=total_cost,
            traces=tuple(traces),
        )

    def _run_step(self, turn: TurnInfo, input_tokens: int) -> StepTrace:
        self.budget_pressure = live_budget_pressure(self.governor, init=self._pressure_init)
        expected_costs = {
            backend.name: self.governor.estimate_cost(
                backend,
                input_tokens=input_tokens,
                expected_output_tokens=max(8, round(backend.mean_output_tokens * STAGE_OUTPUT_MULTIPLIER[turn.stage])),
            ).expected_cost
            for backend in self.backends
        }
        if self.backend_picker is None:
            backend = self.selector.select_backend(
                turn_info=turn,
                backends=self.backends,
                budget_pressure=self.budget_pressure,
                expected_costs=expected_costs,
            ).backend
        else:
            backend = self.backend_picker(
                turn,
                self.backends,
                self.selector,
                self.budget_pressure,
                expected_costs,
            )
        scheduler_decision = self.scheduler.decide(
            can_dispatch_preferred=self.governor.can_dispatch(backend),
        )
        if scheduler_decision is SchedulerDecision.REJECT:
            return StepTrace(
                workflow_id=turn.workflow_id,
                step_index=turn.step_index,
                stage=turn.stage,
                chosen_backend=backend.name,
                scheduler_decision=scheduler_decision.value,
                progress_made=False,
                actual_cost=0.0,
                status=WorkflowStatus.FAILED.value,
            )
        if scheduler_decision is SchedulerDecision.QUEUE:
            self.scheduler.complete_queued()

        estimate = self.governor.estimate_cost(backend, input_tokens=input_tokens)
        reservation = self.governor.reserve(turn.workflow_id, backend, estimate)
        if reservation is None:
            return StepTrace(
                workflow_id=turn.workflow_id,
                step_index=turn.step_index,
                stage=turn.stage,
                chosen_backend=backend.name,
                scheduler_decision=SchedulerDecision.REJECT.value,
                progress_made=False,
                actual_cost=0.0,
                status=WorkflowStatus.FAILED.value,
            )

        self.ledger.start_step(turn.workflow_id, turn.step_index, backend.name, reservation.reservation_id)
        if self.backend_runner is not None:
            result = self.backend_runner(backend, turn, input_tokens)
        else:
            result = self.mock_backends[backend.name].run(turn, input_tokens=input_tokens)
        actual_cost = backend.cost_per_input_token * result.input_tokens + backend.cost_per_output_token * result.output_tokens

        if result.timed_out:
            self.governor.release(reservation.reservation_id, WorkflowStatus.ZOMBIE)
            return StepTrace(
                workflow_id=turn.workflow_id,
                step_index=turn.step_index,
                stage=turn.stage,
                chosen_backend=backend.name,
                scheduler_decision=scheduler_decision.value,
                progress_made=False,
                actual_cost=0.0,
                status=WorkflowStatus.ZOMBIE.value,
            )

        self.governor.settle(reservation.reservation_id, actual_cost=actual_cost, status=WorkflowStatus.COMPLETED)
        return StepTrace(
            workflow_id=turn.workflow_id,
            step_index=turn.step_index,
            stage=turn.stage,
            chosen_backend=backend.name,
            scheduler_decision=scheduler_decision.value,
            progress_made=result.progress_made,
            actual_cost=actual_cost,
            status=WorkflowStatus.COMPLETED.value,
            response_text=result.response_text,
        )

def build_default_loop(
    backends: list[Backend],
    governor: BudgetGovernor,
    ledger: WorkflowLedgerStore,
    budget_pressure: float,
    *,
    progress_table: ProgressTable,
    queue_limit: int = 0,
    zombie_timeout_seconds: float = 5.0,
    backend_picker: Callable[[TurnInfo, list[Backend], BudgetFlowSelector, float, dict[str, float]], Backend] | None = None,
    backend_runner: Callable[[Backend, TurnInfo, int], BackendCallResult] | None = None,
) -> MinimalAgentLoop:
    selector = BudgetFlowSelector(progress_table)
    scheduler = WorkflowScheduler(queue_limit=queue_limit)
    zombie_detector = ZombieDetector(timeout_seconds=zombie_timeout_seconds)
    return MinimalAgentLoop(
        backends=backends,
        governor=governor,
        ledger=ledger,
        selector=selector,
        scheduler=scheduler,
        zombie_detector=zombie_detector,
        budget_pressure=budget_pressure,
        backend_picker=backend_picker,
        backend_runner=backend_runner,
    )
