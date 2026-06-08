from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .types import Backend


@dataclass(frozen=True)
class TokenCostBand:
    max_input_tokens: int | None
    input_per_1m: float
    output_per_1m: float


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
    token_cost_bands: tuple[TokenCostBand, ...] = ()
    rpm_limit: int = 0
    concurrency_limit: int = 0
    protocol: str = "tool_call"
    api_base_env: str | None = None
    proxy_env: str | None = None
    cost_source: str = "manual"
    cost_updated: str = "unknown"
    cost_notes: str = ""
    progress_source: str = "manual"
    progress_updated: str = "unknown"
    progress_notes: str = ""


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
        cost_per_input_token=0.30 / 1_000_000,
        cost_per_output_token=1.50 / 1_000_000,
        token_cost_bands=(
            TokenCostBand(32_000, 0.30, 1.50),
            TokenCostBand(128_000, 0.50, 2.50),
            TokenCostBand(256_000, 0.80, 4.00),
            TokenCostBand(1_000_000, 1.60, 9.60),
        ),
        mean_output_tokens=768,
        progress_score=0.15,
        latency_ms=500,
        progress_prior={"localization": 0.50, "repair": 0.38, "validation": 0.45},
        escalation_patience=4,
        max_turns=20,
        cost_source="Alibaba Cloud Model Studio pricing, qwen3-coder-flash series",
        cost_updated="2026-06-07",
        cost_notes="USD per 1M tokens, input-length tiered; cache discounts intentionally not assumed.",
        progress_source="BudgetFlow heuristic prior, not yet empirically calibrated",
        progress_updated="2026-06-07",
        progress_notes="Must be sensitivity-checked before paper-scale paid runs.",
    ),
    TierConfig(
        tier=2,
        backend=TIER2_BACKEND,
        model="openai/qwen3.7-max",
        provider="openai_compatible",
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        display="qwen3.7-max",
        cost_per_input_token=1.68 / 1_000_000,
        cost_per_output_token=5.04 / 1_000_000,
        token_cost_bands=(
            TokenCostBand(1_000_000, 1.68, 5.04),
        ),
        mean_output_tokens=1024,
        progress_score=0.24,
        latency_ms=1100,
        progress_prior={"localization": 0.67, "repair": 0.65, "validation": 0.63},
        escalation_patience=5,
        max_turns=35,
        cost_source="Alibaba Cloud Model Studio pricing, qwen3.7-max",
        cost_updated="2026-06-07",
        cost_notes="Canonical USD estimate converted from public mainland CNY pricing ¥12 input / ¥36 output per 1M tokens at ~7.14 CNY/USD; cache discounts and promotions intentionally not assumed. Verify against DashScope billing before paper-scale paid runs.",
        progress_source="BudgetFlow heuristic prior after catalog swap from qwen3-coder-plus to qwen3.7-max; not yet empirically calibrated",
        progress_updated="2026-06-07",
        progress_notes="Must be sensitivity-checked before paper-scale paid runs.",
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
        cost_source="AICode007 configured GPT-5.4 proxy price",
        cost_updated="2026-06-07",
        cost_notes="USD per 1M tokens from configured proxy rate; verify against account billing before paper-scale paid runs.",
        progress_source="BudgetFlow heuristic prior, not yet empirically calibrated",
        progress_updated="2026-06-07",
        progress_notes="Must be sensitivity-checked before paper-scale paid runs.",
    ),
)


def _looks_like_iso_date(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


def validate_tier_catalog(configs: tuple[TierConfig, ...] = DEFAULT_TIER_CONFIGS) -> list[str]:
    """Return catalog confidence problems that should block paid experiments.

    The price table is part of the evaluation harness. If it is stale or
    unexplained, T1 value-per-dollar and routing thresholds become suspect.
    """
    issues: list[str] = []
    for cfg in configs:
        if cfg.cost_per_input_token <= 0 or cfg.cost_per_output_token <= 0:
            issues.append(f"{cfg.backend}: non-positive token cost")
        if not cfg.cost_source or cfg.cost_source == "manual":
            issues.append(f"{cfg.backend}: missing cost source confidence")
        if not _looks_like_iso_date(cfg.cost_updated):
            issues.append(f"{cfg.backend}: missing cost_updated YYYY-MM-DD")
        if not cfg.progress_source or cfg.progress_source == "manual":
            issues.append(f"{cfg.backend}: missing progress source confidence")
        if not _looks_like_iso_date(cfg.progress_updated):
            issues.append(f"{cfg.backend}: missing progress_updated YYYY-MM-DD")
        for stage, value in cfg.progress_prior.items():
            if not 0.0 <= value <= 1.0:
                issues.append(f"{cfg.backend}: invalid progress_prior {stage}={value}")
    return issues


def catalog_revision(configs: tuple[TierConfig, ...] = DEFAULT_TIER_CONFIGS) -> str:
    """Small stable revision id for cost/progress catalog confidence."""
    parts = [
        f"{cfg.backend}:{cfg.cost_updated}:{cfg.progress_updated}"
        for cfg in sorted(configs, key=lambda item: item.backend)
    ]
    return "|".join(parts)


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
    def second_cheapest(backends: list[Backend]) -> Backend:
        ordered = sorted(backends, key=lambda backend: backend.tier)
        return ordered[1] if len(ordered) >= 2 else ordered[0]

    @staticmethod
    def at_or_above(backends: list[Backend], tier: int) -> Backend:
        ordered = sorted(backends, key=lambda backend: backend.tier)
        return next((backend for backend in ordered if backend.tier >= tier), ordered[-1])

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


def token_cost_rates(backend_name: str, input_tokens: int) -> tuple[float, float]:
    """Return per-token input/output cost for this request size."""
    config = MODEL_CATALOG.require_config(backend_name)
    for band in config.token_cost_bands:
        if band.max_input_tokens is None or input_tokens <= band.max_input_tokens:
            return band.input_per_1m / 1_000_000, band.output_per_1m / 1_000_000
    if config.token_cost_bands:
        band = config.token_cost_bands[-1]
        return band.input_per_1m / 1_000_000, band.output_per_1m / 1_000_000
    return config.cost_per_input_token, config.cost_per_output_token


def estimate_token_cost(backend_name: str, *, input_tokens: int, output_tokens: int) -> float:
    input_rate, output_rate = token_cost_rates(backend_name, input_tokens)
    return input_tokens * input_rate + output_tokens * output_rate


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


def tier_confidence(backend_name: str) -> dict[str, str]:
    config = MODEL_CATALOG.config_for(backend_name)
    if config is None:
        return {}
    return {
        "cost_source": config.cost_source,
        "cost_updated": config.cost_updated,
        "cost_notes": config.cost_notes,
        "progress_source": config.progress_source,
        "progress_updated": config.progress_updated,
        "progress_notes": config.progress_notes,
    }


def parse_tier_label(value: object) -> int:
    """Best-effort tier id parser for labels like ``tier2`` or ``T4``."""
    match = re.search(r"(?:tier|t)(\d+)(?!\d)", str(value).lower())
    return int(match.group(1)) if match else 0
