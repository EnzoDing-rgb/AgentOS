"""SWE-bench segment adapter: maps LOCALIZATION/REPAIR/VALIDATION to BudgetFlow segments.

BudgetFlow uses three coarse workflow segments as policy signals:
  Context -> LOCALIZATION  (gather information, inspect state)
  Action  -> REPAIR        (edit, write, change task state)
  Verification -> VALIDATION (check whether the change worked)

The mapping is a SWE-bench adapter detail. Enterprise adapters map their
own phases onto these segments (triage/action/review, retrieval/drafting/
checking, analysis/execution/QA, etc.).
"""

from __future__ import annotations

from typing import Protocol

from ..types import Stage, WorkflowSegment


class WorkflowAdapter(Protocol):
    def to_segment(self, stage: Stage, **signals: float | str | bool) -> WorkflowSegment: ...


class SwebenchSegmentAdapter:
    """Maps SWE-bench workflow stages to BudgetFlow WorkflowSegments.

    This is a thin mapping adapter. BudgetFlow Mechanism only sees
    Context / Action / Verification. The SWE-bench terms
    LOCALIZATION / REPAIR / VALIDATION stay inside this adapter.
    """

    # Bidirectional mapping
    _STAGE_TO_SEGMENT: dict[Stage, str] = {
        Stage.LOCALIZATION: WorkflowSegment.CONTEXT,
        Stage.REPAIR: WorkflowSegment.ACTION,
        Stage.VALIDATION: WorkflowSegment.VERIFICATION,
    }

    _SEGMENT_TO_STAGE: dict[str, Stage] = {
        WorkflowSegment.CONTEXT: Stage.LOCALIZATION,
        WorkflowSegment.ACTION: Stage.REPAIR,
        WorkflowSegment.VERIFICATION: Stage.VALIDATION,
    }

    def to_segment(self, stage: Stage, **signals: float | str | bool) -> WorkflowSegment:
        """Convert a SWE-bench stage to a BudgetFlow workflow segment."""
        name = self._STAGE_TO_SEGMENT.get(stage, WorkflowSegment.CONTEXT)
        return WorkflowSegment(name=name, signals=dict(signals))

    def to_stage(self, segment: WorkflowSegment) -> Stage:
        """Convert a BudgetFlow workflow segment back to a SWE-bench stage."""
        return self._SEGMENT_TO_STAGE.get(segment.name, Stage.LOCALIZATION)

    @property
    def segment_names(self) -> tuple[str, ...]:
        return (WorkflowSegment.CONTEXT, WorkflowSegment.ACTION, WorkflowSegment.VERIFICATION)

    @property
    def stage_names(self) -> tuple[str, ...]:
        return tuple(s.value for s in Stage)


def segment_from_stage(stage: Stage, **signals: float | str | bool) -> WorkflowSegment:
    """Convenience: convert a stage to a segment without constructing the adapter."""
    mapping = {
        Stage.LOCALIZATION: WorkflowSegment.CONTEXT,
        Stage.REPAIR: WorkflowSegment.ACTION,
        Stage.VALIDATION: WorkflowSegment.VERIFICATION,
    }
    return WorkflowSegment(name=mapping.get(stage, WorkflowSegment.CONTEXT), signals=dict(signals))
