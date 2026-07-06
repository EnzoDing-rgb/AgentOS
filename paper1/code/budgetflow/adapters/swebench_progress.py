"""SWE-bench progress adapter.

This adapter keeps bash-command and agent-phase heuristics behind the
SWE-bench boundary. BudgetFlow policies consume normalized workflow segments
and progress/outcome signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..adapter.bash_stage import (
    actions_count_as_progress,
    classify_routing_stage,
    command_counts_as_progress,
    extract_trace_file_paths,
)
from ..types import Stage, WorkflowSegment
from .swebench_segment import SwebenchSegmentAdapter


@dataclass(frozen=True)
class ProgressSignal:
    stage: Stage
    segment: WorkflowSegment
    has_progress: bool | None
    progress_reason: str
    touched_file_paths: list[str] = field(default_factory=list)

    def as_record(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "workflow_segment": self.segment.name,
            "segment_signals": dict(self.segment.signals),
            "has_progress": self.has_progress,
            "progress_reason": self.progress_reason,
            "touched_file_paths": list(self.touched_file_paths),
        }


@dataclass(frozen=True)
class ActionProgressSignal:
    has_progress: bool | None
    progress_reason: str


@dataclass(frozen=True)
class VerifiedOutcome:
    resolved: bool
    detail: str
    patch_extracted: bool
    patch_source: str
    submitted_patch: str | None
    workspace_patch: str | None

    def as_record(self) -> dict[str, Any]:
        return {
            "harness_resolved": self.resolved,
            "patch_extracted": self.patch_extracted,
            "patch_source": self.patch_source,
            "submitted_patch": self.submitted_patch,
            "workspace_patch": self.workspace_patch,
            "detail": self.detail,
        }


class ProgressAdapter(Protocol):
    def signal_from_context(
        self,
        *,
        bash_command: str | None,
        observation: str | None = None,
        agent_phase: str | None = None,
        assistant_content_head: str | None = None,
        parser_input_snippet: str | None = None,
    ) -> ProgressSignal: ...

    def signal_from_actions(self, actions: list[dict] | tuple[dict, ...] | None) -> ActionProgressSignal: ...
    def outcome_from_result(self, result: Any) -> VerifiedOutcome: ...


class SwebenchProgressAdapter:
    """Normalize mini-SWE traces and harness results into BudgetFlow signals.

    Progress is optional diagnostic evidence. If a task type cannot provide a
    trustworthy intermediate signal, adapters should emit unknown/no-signal
    rather than invent a score. Final acceptance remains the resolved outcome.
    """

    def __init__(self, segment_adapter: SwebenchSegmentAdapter | None = None) -> None:
        self._segment_adapter = segment_adapter or SwebenchSegmentAdapter()

    def signal_from_context(
        self,
        *,
        bash_command: str | None,
        observation: str | None = None,
        agent_phase: str | None = None,
        assistant_content_head: str | None = None,
        parser_input_snippet: str | None = None,
    ) -> ProgressSignal:
        stage = classify_routing_stage(bash_command, observation, agent_phase=agent_phase)
        has_progress, progress_reason = command_counts_as_progress(
            bash_command,
            agent_phase=agent_phase,
        )
        touched = extract_trace_file_paths(
            bash_command=bash_command,
            assistant_content_head=assistant_content_head,
            parser_input_snippet=parser_input_snippet,
        )
        segment = self._segment_adapter.to_segment(
            stage,
            agent_phase=str(agent_phase or ""),
            progress_reason=progress_reason,
            touched_files=len(touched),
        )
        return ProgressSignal(
            stage=stage,
            segment=segment,
            has_progress=has_progress,
            progress_reason=progress_reason,
            touched_file_paths=touched,
        )

    def signal_from_actions(self, actions: list[dict] | tuple[dict, ...] | None) -> ActionProgressSignal:
        has_progress, reason = actions_count_as_progress(actions)
        return ActionProgressSignal(has_progress=has_progress, progress_reason=reason)

    def outcome_from_result(self, result: Any) -> VerifiedOutcome:
        patch_text = getattr(result, "patch_text", None)
        return VerifiedOutcome(
            resolved=bool(getattr(result, "harness_resolved", False)),
            detail=str(getattr(result, "harness_detail", "") or ""),
            patch_extracted=bool(patch_text),
            patch_source=str(getattr(result, "patch_source", "") or "none"),
            submitted_patch=getattr(result, "submitted_patch_path", None),
            workspace_patch=getattr(result, "workspace_patch_path", None),
        )
