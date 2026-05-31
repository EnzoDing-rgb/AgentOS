from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

from .lite_tasks import LiteTaskRecord, build_lite_stage_prompt
from .types import Backend, BackendCallResult, Stage, TurnInfo


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


_PROXY_KEYS = (
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
)


def ensure_direct_api() -> None:
    """DeepSeek 官方 API 直连，清掉 shell/.env 里的代理。"""
    for key in _PROXY_KEYS:
        os.environ.pop(key, None)


def ensure_aicode007_proxy() -> None:
    """aicode007 走 HTTP 代理：优先 shell http_proxy，否则 .env 的 AICODE007_HTTP_PROXY。

    Clears ALL_PROXY/all_proxy so httpx/litellm do not pick up SOCKS (needs socksio).
    """
    proxy = (
        os.environ.get("http_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("AICODE007_HTTP_PROXY")
    )
    if not proxy:
        return
    os.environ["http_proxy"] = proxy
    os.environ["https_proxy"] = proxy
    os.environ["HTTP_PROXY"] = proxy
    os.environ["HTTPS_PROXY"] = proxy
    for key in ("all_proxy", "ALL_PROXY"):
        os.environ.pop(key, None)


def load_env_file() -> None:
    env_path = _repo_root() / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def extract_message_text(message) -> str:
    content = (getattr(message, "content", None) or "").strip()
    if content:
        return content
    reasoning = getattr(message, "reasoning_content", None)
    if reasoning:
        return str(reasoning).strip()
    return ""


def default_stage_prompt(turn_info: TurnInfo, input_tokens: int) -> str:
    return (
        f"Stage={turn_info.stage.value}\n"
        f"Workflow={turn_info.workflow_id}\n"
        f"Step={turn_info.step_index}\n"
        f"ApproxInputTokens={input_tokens}\n"
        "Reply with one short sentence describing the most important next action."
    )


def evaluate_react_progress(stage: Stage, action: str | None, tool_ok: bool) -> bool:
    if not action:
        return False
    if stage is Stage.LOCALIZATION:
        return tool_ok and action in {"read_file", "grep", "glob", "search_defs", "finish_localization"}
    if stage is Stage.REPAIR:
        return tool_ok and action in {"apply_edits", "submit_patch"}
    return tool_ok


def evaluate_step_progress(stage: Stage, text: str) -> bool:
    cleaned = text.strip()
    if len(cleaned) < 20:
        return False
    lower = cleaned.lower()
    if stage is Stage.LOCALIZATION:
        return ".py" in lower or "/" in cleaned or "file" in lower
    if stage is Stage.REPAIR:
        if '"edits"' in cleaned and "{" in cleaned:
            return True
        return any(token in lower for token in ("fix", "patch", "change", "bug", "cause", "def ", "class "))
    return any(token in lower for token in ("test", "verify", "valid", "assert", "pass", "fail"))


@dataclass(frozen=True)
class DeepSeekBackend:
    backend: Backend
    model_name: str
    api_key: str | None = None
    base_url: str = "https://api.deepseek.com"
    enable_thinking: bool | None = None
    reasoning_effort: str | None = None
    get_task: Callable[[str], LiteTaskRecord | None] | None = None
    prompt_builder: Callable[[TurnInfo, int], str] | None = None
    stage_max_tokens: dict[Stage, int] | None = None
    stage_enable_thinking: dict[Stage, bool] | None = None

    def complete_chat(self, messages: list[dict[str, str]], stage: Stage) -> BackendCallResult:
        load_env_file()
        ensure_direct_api()
        api_key = self.api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is missing. Add it to the repo root .env file.")

        client = OpenAI(api_key=api_key, base_url=self.base_url)
        thinking_enabled = self._thinking_enabled_for_stage(stage)
        kwargs: dict = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "max_tokens": self._max_tokens_for_stage(stage),
            "extra_body": {"thinking": {"type": "enabled" if thinking_enabled else "disabled"}},
        }
        if thinking_enabled:
            kwargs["reasoning_effort"] = self.reasoning_effort or "high"
        response = client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        text = extract_message_text(message)
        usage = response.usage
        output_tokens = getattr(usage, "completion_tokens", None) or self.backend.mean_output_tokens
        prompt_tokens = getattr(usage, "prompt_tokens", None) or 1
        return BackendCallResult(
            backend_name=self.backend.name,
            input_tokens=prompt_tokens,
            output_tokens=output_tokens,
            progress_made=False,
            latency_ms=self.backend.latency_ms,
            timed_out=False,
            response_text=text,
        )

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

        load_env_file()
        ensure_direct_api()
        api_key = self.api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is missing. Add it to the repo root .env file.")

        client = OpenAI(api_key=api_key, base_url=self.base_url)
        user_prompt = self._build_user_prompt(turn_info, input_tokens)
        request_kwargs = self._build_request_kwargs(user_prompt, turn_info.stage)
        response = client.chat.completions.create(**request_kwargs)

        message = response.choices[0].message
        text = extract_message_text(message)
        usage = response.usage
        output_tokens = getattr(usage, "completion_tokens", None) or self.backend.mean_output_tokens
        prompt_tokens = getattr(usage, "prompt_tokens", None) or input_tokens
        progress_made = evaluate_step_progress(turn_info.stage, text)
        return BackendCallResult(
            backend_name=self.backend.name,
            input_tokens=prompt_tokens,
            output_tokens=output_tokens,
            progress_made=progress_made,
            latency_ms=self.backend.latency_ms,
            timed_out=False,
            response_text=text,
        )

    def _build_user_prompt(self, turn_info: TurnInfo, input_tokens: int) -> str:
        if self.prompt_builder is not None:
            return self.prompt_builder(turn_info, input_tokens)
        if self.get_task is not None:
            task = self.get_task(turn_info.workflow_id)
            if task is not None:
                return build_lite_stage_prompt(task, turn_info.stage)
        return default_stage_prompt(turn_info, input_tokens)

    def _build_request_kwargs(self, user_prompt: str, stage: Stage) -> dict:
        thinking_enabled = self._thinking_enabled_for_stage(stage)
        system_content = (
            "You are a software repair agent working on a real bug report. "
            "Answer concisely and concretely."
        )
        if stage is Stage.REPAIR:
            system_content = (
                "You are a software repair agent. Output ONLY one valid JSON object "
                "inside a ```json code block with an `edits` array. No prose outside JSON."
            )
        kwargs: dict = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": system_content,
                },
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "max_tokens": self._max_tokens_for_stage(stage),
            "extra_body": {"thinking": {"type": "enabled" if thinking_enabled else "disabled"}},
        }
        if thinking_enabled:
            kwargs["reasoning_effort"] = self.reasoning_effort or "high"
        return kwargs

    def _thinking_enabled(self) -> bool:
        if self.enable_thinking is not None:
            return self.enable_thinking
        if self.model_name.endswith("-pro"):
            return True
        return False

    def _thinking_enabled_for_stage(self, stage: Stage) -> bool:
        if self.stage_enable_thinking and stage in self.stage_enable_thinking:
            return self.stage_enable_thinking[stage]
        if stage is Stage.REPAIR:
            return False
        return self._thinking_enabled()

    def _max_tokens_for_stage(self, stage: Stage) -> int:
        if self.stage_max_tokens and stage in self.stage_max_tokens:
            return self.stage_max_tokens[stage]
        return self.backend.mean_output_tokens
