from __future__ import annotations

import os
from dataclasses import dataclass

from openai import OpenAI

from .types import Backend, BackendCallResult, TurnInfo


@dataclass(frozen=True)
class DeepSeekBackend:
    backend: Backend
    model_name: str
    api_key: str | None = None
    base_url: str = "https://api.deepseek.com"

    def run(self, turn_info: TurnInfo, input_tokens: int, forced_timeout: bool = False) -> BackendCallResult:
        if forced_timeout:
            return BackendCallResult(
                backend_name=self.backend.name,
                input_tokens=input_tokens,
                output_tokens=0,
                progress_made=False,
                latency_ms=self.backend.latency_ms,
                timed_out=True,
            )

        client = OpenAI(
            api_key=self.api_key or os.environ.get("DEEPSEEK_API_KEY"),
            base_url=self.base_url,
        )
        response = client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": "You are helping evaluate BudgetFlow routing decisions."},
                {
                    "role": "user",
                    "content": (
                        f"Stage={turn_info.stage.value}\n"
                        f"Workflow={turn_info.workflow_id}\n"
                        f"Step={turn_info.step_index}\n"
                        f"ApproxInputTokens={input_tokens}\n"
                        "Reply with one short sentence describing the most important next action."
                    ),
                },
            ],
            stream=False,
            max_tokens=self.backend.mean_output_tokens,
        )
        usage = response.usage
        output_tokens = getattr(usage, "completion_tokens", None) or self.backend.mean_output_tokens
        prompt_tokens = getattr(usage, "prompt_tokens", None) or input_tokens
        content = response.choices[0].message.content or ""
        progress_made = bool(content.strip())
        return BackendCallResult(
            backend_name=self.backend.name,
            input_tokens=prompt_tokens,
            output_tokens=output_tokens,
            progress_made=progress_made,
            latency_ms=self.backend.latency_ms,
            timed_out=False,
        )
