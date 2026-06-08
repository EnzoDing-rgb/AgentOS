"""BudgetFlow architectural adapters: segment, progress, task, value, cost, verifier.

These adapters keep SWE-bench specifics behind clean contracts so
BudgetFlow core stays benchmark-agnostic.
"""

from .swebench_segment import SwebenchSegmentAdapter, segment_from_stage
from .swebench_value import SwebenchValueAdapter, ValueAdapter, ValueEstimate
from .swebench_cost import CostAdapter, CostEstimate, SwebenchCostAdapter
from .swebench_task import SwebenchTaskAdapter, TaskAdapter, TaskFeatures
from .swebench_verifier import SwebenchVerifierAdapter, VerifierAdapter, VerifiedOutcome
from .swebench_runtime import MiniSweRuntimeAdapter, RuntimeAdapter
from .swebench_progress import (
    ActionProgressSignal,
    ProgressAdapter,
    ProgressSignal,
    SwebenchProgressAdapter,
)

__all__ = [
    "CostAdapter",
    "CostEstimate",
    "MiniSweRuntimeAdapter",
    "ActionProgressSignal",
    "ProgressAdapter",
    "ProgressSignal",
    "RuntimeAdapter",
    "SwebenchCostAdapter",
    "SwebenchProgressAdapter",
    "SwebenchSegmentAdapter",
    "SwebenchTaskAdapter",
    "SwebenchValueAdapter",
    "SwebenchVerifierAdapter",
    "TaskAdapter",
    "TaskFeatures",
    "ValueAdapter",
    "ValueEstimate",
    "VerifierAdapter",
    "VerifiedOutcome",
    "segment_from_stage",
]
