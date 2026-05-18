from __future__ import annotations

from dataclasses import dataclass

from .types import Backend, BackendCallResult, Stage, TurnInfo


@dataclass(frozen=True)
class MockBackend:
    backend: Backend

    def run(self, turn_info: TurnInfo, input_tokens: int, forced_timeout: bool = False) -> BackendCallResult:
        output_tokens = self.backend.mean_output_tokens
        progress_threshold = {
            Stage.LOCALIZATION: 0.12,
            Stage.REPAIR: 0.18,
            Stage.VALIDATION: 0.15,
        }[turn_info.stage]
        progress_made = self.backend.progress_score >= progress_threshold
        return BackendCallResult(
            backend_name=self.backend.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            progress_made=progress_made,
            latency_ms=self.backend.latency_ms,
            timed_out=forced_timeout,
        )
