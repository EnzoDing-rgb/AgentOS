"""SWE-bench verifier adapter.

The mini-SWE runner returns harness-specific fields. This adapter converts them
into the outcome and evidence fields that BudgetFlow records and audits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class VerifiedOutcome:
    resolved: bool
    detail: str
    patch_extracted: bool
    patch_source: str
    submitted_patch: str | None

    def as_record(self) -> dict[str, Any]:
        return {
            "harness_resolved": self.resolved,
            "resolved": self.resolved,
            "patch_extracted": self.patch_extracted,
            "patch_source": self.patch_source,
            "submitted_patch": self.submitted_patch,
            "detail": self.detail,
        }


class VerifierAdapter(Protocol):
    def outcome_from_result(self, result: Any) -> VerifiedOutcome: ...


class SwebenchVerifierAdapter:
    """Normalize mini-SWE harness result fields."""

    def outcome_from_result(self, result: Any) -> VerifiedOutcome:
        patch_text = getattr(result, "patch_text", None)
        return VerifiedOutcome(
            resolved=bool(getattr(result, "harness_resolved", False)),
            detail=str(getattr(result, "harness_detail", "") or ""),
            patch_extracted=bool(patch_text),
            patch_source=str(getattr(result, "patch_source", "") or "none"),
            submitted_patch=getattr(result, "submitted_patch_path", None),
        )
