from __future__ import annotations

import os
from dataclasses import dataclass

from .types import Backend


@dataclass(frozen=True)
class TierConfig:
    tier: int
    backend: str
    model: str
    provider: str
    api_base: str
    api_key_env: str
    display: str
    cost_per_input_token: float
    cost_per_output_token: float
    mean_output_tokens: int
    progress_score: float
    latency_ms: int
    progress_prior: dict[str, float]
    escalation_patience: int | None
    max_turns: int | None
    rpm_limit: int = 0
    concurrency_limit: int = 0
    protocol: str = "tool_call"
    api_base_env: str | None = None
    proxy_env: str | None = None


_CNY_TO_USD = 1.0 / 7.25

TIER1_BACKEND = "tier1"
TIER2_BACKEND = "tier2"
TIER3_BACKEND = "tier3"

DEFAULT_TIER_CONFIGS: tuple[TierConfig, ...] = (
    TierConfig(
        tier=1,
        backend=TIER1_BACKEND,
        model="openai/qwen3-coder-flash",
        provider="openai_compatible",
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        display="qwen3-coder-flash",
        cost_per_input_token=0.0004 / 1000 * _CNY_TO_USD,
        cost_per_output_token=0.002 / 1000 * _CNY_TO_USD,
        mean_output_tokens=768,
        progress_score=0.15,
        latency_ms=500,
        progress_prior={"localization": 0.50, "repair": 0.38, "validation": 0.45},
        escalation_patience=4,
        max_turns=20,
    ),
    TierConfig(
        tier=2,
        backend=TIER2_BACKEND,
        model="openai/qwen3-coder-plus",
        provider="openai_compatible",
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        display="qwen3-coder-plus",
        cost_per_input_token=0.004 / 1000 * _CNY_TO_USD,
        cost_per_output_token=0.016 / 1000 * _CNY_TO_USD,
        mean_output_tokens=1024,
        progress_score=0.22,
        latency_ms=900,
        progress_prior={"localization": 0.65, "repair": 0.62, "validation": 0.60},
        escalation_patience=5,
        max_turns=35,
    ),
    TierConfig(
        tier=3,
        backend=TIER3_BACKEND,
        model="openai/gpt-5.4",
        provider="openai_compatible",
        api_base="https://api.aicode007.com/v1",
        api_key_env="AICODE007_API_KEY",
        display="GPT-5.4",
        cost_per_input_token=2.50 / 1_000_000,
        cost_per_output_token=15.00 / 1_000_000,
        mean_output_tokens=1024,
        progress_score=0.25,
        latency_ms=1200,
        progress_prior={"localization": 0.68, "repair": 0.68, "validation": 0.66},
        escalation_patience=5,
        max_turns=None,
        protocol="text_regex",
        api_base_env="AICODE007_BASE_URL",
        proxy_env="AICODE007_HTTP_PROXY",
    ),
)


def load_env_file() -> None:
    from pathlib import Path

    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def apply_provider_proxy(config: TierConfig) -> None:
    if not config.proxy_env:
        return
    proxy = (
        os.environ.get("http_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get(config.proxy_env)
    )
    if not proxy:
        return
    os.environ["http_proxy"] = proxy
    os.environ["https_proxy"] = proxy
    os.environ["HTTP_PROXY"] = proxy
    os.environ["HTTPS_PROXY"] = proxy
    for key in ("all_proxy", "ALL_PROXY"):
        os.environ.pop(key, None)


class ModelCatalog:
    """Provider-agnostic tier registry for BudgetFlow runtime and experiments."""

    def __init__(self, configs: tuple[TierConfig, ...] = DEFAULT_TIER_CONFIGS) -> None:
        ordered = tuple(sorted(configs, key=lambda cfg: cfg.tier))
        if not ordered:
            raise ValueError("model tier pool cannot be empty")
        tiers = [cfg.tier for cfg in ordered]
        if len(set(tiers)) != len(tiers):
            raise ValueError(f"duplicate model tiers: {tiers}")
        self._configs = ordered
        self._by_backend = {cfg.backend: cfg for cfg in ordered}

    @property
    def configs(self) -> tuple[TierConfig, ...]:
        return self._configs

    @property
    def backend_names(self) -> tuple[str, ...]:
        return tuple(cfg.backend for cfg in self._configs)

    def config_for(self, backend_name: str) -> TierConfig | None:
        return self._by_backend.get(backend_name)

    def require_config(self, backend_name: str) -> TierConfig:
        config = self.config_for(backend_name)
        if config is None:
            raise ValueError(f"unknown backend: {backend_name}")
        return config

    def backends(self) -> list[Backend]:
        return [
            Backend(
                name=cfg.backend,
                tier=cfg.tier,
                cost_per_input_token=cfg.cost_per_input_token,
                cost_per_output_token=cfg.cost_per_output_token,
                rpm_limit=cfg.rpm_limit,
                concurrency_limit=cfg.concurrency_limit,
                mean_output_tokens=cfg.mean_output_tokens,
                progress_score=cfg.progress_score,
                latency_ms=cfg.latency_ms,
            )
            for cfg in self._configs
        ]

    @staticmethod
    def cheapest(backends: list[Backend]) -> Backend:
        return sorted(backends, key=lambda backend: backend.tier)[0]

    @staticmethod
    def strongest(backends: list[Backend]) -> Backend:
        return sorted(backends, key=lambda backend: backend.tier)[-1]

    @staticmethod
    def tier(backends: list[Backend], n: int) -> Backend:
        ordered = sorted(backends, key=lambda backend: backend.tier)
        return next((backend for backend in ordered if backend.tier == n), ordered[-1])

    @staticmethod
    def next_higher(backends: list[Backend], backend: Backend) -> Backend | None:
        return next((candidate for candidate in sorted(backends, key=lambda b: b.tier) if candidate.tier > backend.tier), None)

    @staticmethod
    def next_lower(backends: list[Backend], backend: Backend) -> Backend | None:
        lower = [candidate for candidate in sorted(backends, key=lambda b: b.tier) if candidate.tier < backend.tier]
        return lower[-1] if lower else None

    def litellm_kwargs(self, backend_name: str) -> tuple[str, dict]:
        config = self.require_config(backend_name)
        apply_provider_proxy(config)
        api_base = os.environ.get(config.api_base_env or "") or config.api_base
        return config.model, {
            "temperature": 0.0,
            "parallel_tool_calls": True,
            "drop_params": True,
            "api_base": api_base,
            "api_key": os.environ.get(config.api_key_env),
        }


MODEL_CATALOG = ModelCatalog()
TIER_CONFIGS: dict[str, TierConfig] = {cfg.backend: cfg for cfg in MODEL_CATALOG.configs}


def tier_display_name(backend_name: str) -> str:
    config = MODEL_CATALOG.config_for(backend_name)
    return config.display if config is not None else backend_name


def tier_model_id(backend_name: str) -> str:
    config = MODEL_CATALOG.config_for(backend_name)
    return config.model if config is not None else backend_name


def protocol_for(backend_name: str) -> str:
    config = MODEL_CATALOG.config_for(backend_name)
    return config.protocol if config is not None else "tool_call"
