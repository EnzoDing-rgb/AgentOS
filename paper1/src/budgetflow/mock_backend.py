from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

from .types import Backend, BackendCallResult, Stage, TurnInfo


STAGE_BASE_DIFFICULTY = {
    Stage.LOCALIZATION: 0.13,
    Stage.REPAIR: 0.19,
    Stage.VALIDATION: 0.17,
}

STAGE_TIER_BONUS = {
    Stage.LOCALIZATION: {1: 0.018, 2: 0.043, 3: 0.056, 4: 0.062},
    Stage.REPAIR: {1: -0.015, 2: 0.016, 3: 0.051, 4: 0.081},
    Stage.VALIDATION: {1: -0.006, 2: 0.021, 3: 0.041, 4: 0.067},
}

STAGE_OUTPUT_MULTIPLIER = {
    Stage.LOCALIZATION: 0.8,
    Stage.REPAIR: 1.15,
    Stage.VALIDATION: 1.0,
}


@dataclass(frozen=True)
class MockBackend:
    backend: Backend

    def run(self, turn_info: TurnInfo, input_tokens: int, forced_timeout: bool = False) -> BackendCallResult:
        output_tokens = max(8, round(self.backend.mean_output_tokens * STAGE_OUTPUT_MULTIPLIER[turn_info.stage]))
        capability = self.backend.progress_score + STAGE_TIER_BONUS[turn_info.stage][self.backend.tier]
        difficulty = STAGE_BASE_DIFFICULTY[turn_info.stage] + min(input_tokens / 2000.0, 0.075) + self._workflow_jitter(turn_info)
        success_probability = 1.0 / (1.0 + math.exp(-18.0 * (capability - difficulty)))
        progress_made = success_probability >= self._deterministic_draw(turn_info)
        return BackendCallResult(
            backend_name=self.backend.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            progress_made=progress_made,
            latency_ms=self.backend.latency_ms,
            timed_out=forced_timeout,
        )

    def _workflow_jitter(self, turn_info: TurnInfo) -> float:
        value = self._stable_fraction(f"{turn_info.workflow_id}:{turn_info.step_index}:{turn_info.stage.value}")
        return value * 0.07 - 0.035

    def _deterministic_draw(self, turn_info: TurnInfo) -> float:
        value = self._stable_fraction(f"{turn_info.workflow_id}:{turn_info.step_index}:{self.backend.name}")
        return 0.08 + value * 0.84

    def _stable_fraction(self, key: str) -> float:
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") / float(2**64 - 1)
