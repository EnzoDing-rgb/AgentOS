from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

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
        protocol="tool_call",
        cost_source="BudgetFlow normalized experimental cost unit for Qwen3-Coder-Flash T1",
        cost_updated="2026-06-16",
        cost_notes="Virtual experiment units, not public Alibaba Cloud billing. T1 is the cheap reference tier; active mainline currently uses T2/T3, with T1 reserved for diagnostics and future low-cost routing.",
        progress_source="BudgetFlow heuristic prior, not yet empirically calibrated",
        progress_updated="2026-06-07",
        progress_notes="Must be sensitivity-checked before paper-scale paid runs.",
    ),
    TierConfig(
        tier=2,
        backend=TIER2_BACKEND,
        model="openai/qwen3.7-plus",
        provider="openai_compatible",
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        display="qwen3.7-plus",
        cost_per_input_token=0.90 / 1_000_000,
        cost_per_output_token=4.50 / 1_000_000,
        token_cost_bands=(
            TokenCostBand(1_000_000, 0.90, 4.50),
        ),
        mean_output_tokens=1024,
        progress_score=0.24,
        latency_ms=4200,
        progress_prior={"localization": 0.67, "repair": 0.65, "validation": 0.63},
        escalation_patience=5,
        max_turns=35,
        protocol="tool_call",
        cost_source="BudgetFlow normalized experimental cost unit for Qwen3.7-Plus T2",
        cost_updated="2026-06-16",
        cost_notes="Virtual experiment units, not public Alibaba Cloud billing. Current mainline fixes T1:T2:T3 at approximately 1:3:15; use real invoices only for spend accounting, not routing semantics.",
        progress_source="BudgetFlow tier-level heuristic prior after Qwen3.7-Plus protocol fix; not outcome-calibrated",
        progress_updated="2026-06-16",
        progress_notes="Small check established native tool-call compatibility after protocol unification. Do not treat as paper-scale ModelFit calibration.",
    ),
    TierConfig(
        tier=3,
        backend=TIER3_BACKEND,
        model="openai/gpt-5.4",
        provider="openai_compatible",
        api_base="https://api.aicode007.com/v1",
        api_key_env="AICODE007_API_KEY",
        display="GPT-5.4",
        cost_per_input_token=4.50 / 1_000_000,
        cost_per_output_token=22.50 / 1_000_000,
        mean_output_tokens=1024,
        progress_score=0.25,
        latency_ms=1200,
        progress_prior={"localization": 0.68, "repair": 0.68, "validation": 0.66},
        escalation_patience=5,
        max_turns=None,
        protocol="tool_call",
        api_base_env="AICODE007_BASE_URL",
        proxy_env="AICODE007_HTTP_PROXY",
        cost_source="BudgetFlow normalized experimental cost unit for GPT-5.4 T3",
        cost_updated="2026-06-16",
        cost_notes="Virtual experiment units, not public provider billing. Current mainline fixes T1:T2:T3 at approximately 1:3:15.",
        progress_source="BudgetFlow heuristic prior, not yet empirically calibrated",
        progress_updated="2026-06-07",
        progress_notes="Must be sensitivity-checked before paper-scale paid runs.",
    ),
)


def _looks_like_iso_date(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


def validate_tier_catalog(configs: tuple[TierConfig, ...] | None = None) -> list[str]:
    """Return catalog confidence problems that should block paid experiments.

    The price table is part of the evaluation harness. If it is stale or
    unexplained, T1 value-per-dollar and routing thresholds become suspect.

    Defaults to the currently loaded ``MODEL_CATALOG``, not the Python fallback.
    """
    if configs is None:
        configs = MODEL_CATALOG.configs
    issues: list[str] = []
    for cfg in configs:
        if cfg.cost_per_input_token <= 0 or cfg.cost_per_output_token <= 0:
            issues.append(f"{cfg.backend}: non-positive token cost")
        if not cfg.cost_source or cfg.cost_source == "manual":
            issues.append(f"{cfg.backend}: missing cost confidence")
        if not _looks_like_iso_date(cfg.cost_updated):
            issues.append(f"{cfg.backend}: missing cost_updated YYYY-MM-DD")
        if not cfg.progress_source or cfg.progress_source == "manual":
            issues.append(f"{cfg.backend}: missing progress confidence")
        if not _looks_like_iso_date(cfg.progress_updated):
            issues.append(f"{cfg.backend}: missing progress_updated YYYY-MM-DD")
        if cfg.protocol != "tool_call":
            issues.append(
                f"{cfg.backend}: unsupported action protocol {cfg.protocol!r}; "
                "active BudgetFlow runs require tool_call"
            )
        for stage, value in cfg.progress_prior.items():
            if not 0.0 <= value <= 1.0:
                issues.append(f"{cfg.backend}: invalid progress_prior {stage}={value}")
    return issues


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


# ── catalog persistence ────────────────────────────────────────────────────

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[2] / "docs/config/model_tiers.default.json"

_catalog: ModelCatalog | None = None
_catalog_path: Path | None = None
_catalog_revision: str = ""
_catalog_content_hash: str = ""


def _build_tier_config_from_json(data: dict) -> TierConfig:
    """Build a TierConfig from a JSON tier entry. Costs in JSON are per-1M USD."""
    input_1m = float(data["cost_per_input_1m"])
    output_1m = float(data["cost_per_output_1m"])
    bands_raw = data.get("token_cost_bands") or []
    bands = tuple(
        TokenCostBand(
            max_input_tokens=band.get("max_input_tokens"),
            input_per_1m=float(band["input_per_1m"]),
            output_per_1m=float(band["output_per_1m"]),
        )
        for band in bands_raw
    )
    progress_prior_raw = data.get("progress_prior") or {}
    return TierConfig(
        tier=int(data["tier"]),
        backend=str(data["backend"]),
        model=str(data["model"]),
        provider=str(data.get("provider", "openai_compatible")),
        api_base=str(data.get("api_base", "")),
        api_key_env=str(data.get("api_key_env", "")),
        display=str(data.get("display", data.get("model", ""))),
        cost_per_input_token=input_1m / 1_000_000,
        cost_per_output_token=output_1m / 1_000_000,
        token_cost_bands=bands,
        mean_output_tokens=int(data.get("mean_output_tokens", 1024)),
        progress_score=float(data.get("progress_score", 0.5)),
        latency_ms=int(data.get("latency_ms", 800)),
        progress_prior={
            "localization": float(progress_prior_raw.get("localization", 0.5)),
            "repair": float(progress_prior_raw.get("repair", 0.5)),
            "validation": float(progress_prior_raw.get("validation", 0.5)),
        },
        escalation_patience=data.get("escalation_patience"),
        max_turns=data.get("max_turns"),
        rpm_limit=int(data.get("rpm_limit", 0)),
        concurrency_limit=int(data.get("concurrency_limit", 0)),
        protocol=str(data.get("protocol", "tool_call")),
        api_base_env=data.get("api_base_env"),
        proxy_env=data.get("proxy_env"),
        cost_source=str(data.get("cost_source", "json_catalog")),
        cost_updated=str(data.get("cost_updated", "unknown")),
        cost_notes=str(data.get("cost_notes", "")),
        progress_source=str(data.get("progress_source", "json_catalog")),
        progress_updated=str(data.get("progress_updated", "unknown")),
        progress_notes=str(data.get("progress_notes", "")),
    )


def load_tier_configs_from_json(path: Path) -> tuple[TierConfig, ...]:
    """Load tier configs from a JSON catalog file. Costs are per-1M USD in JSON."""
    raw = path.read_text(errors="replace")
    data = json.loads(raw)
    meta = data.get("meta") or {}
    if meta.get("schema_version") != "v1":
        raise ValueError(f"unsupported catalog schema: {meta.get('schema_version')}")
    tiers_raw = data.get("tiers") or []
    if not tiers_raw:
        raise ValueError("catalog has no tiers")
    return tuple(_build_tier_config_from_json(t) for t in tiers_raw)


def _compute_content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def init_catalog(path: Path | None = None) -> ModelCatalog:
    """Replace the module-level catalog from a JSON file.

    If *path* is None, reloads from the default JSON. Falls back to Python
    ``DEFAULT_TIER_CONFIGS`` if the JSON file is missing or invalid.

    Updates ``MODEL_CATALOG`` and ``TIER_CONFIGS`` in-place.
    """
    global _catalog, _catalog_path, _catalog_revision, _catalog_content_hash
    resolved = path or DEFAULT_CATALOG_PATH
    if not resolved.is_file():
        if path is not None:
            raise FileNotFoundError(f"catalog not found: {resolved}")
        _catalog = ModelCatalog(DEFAULT_TIER_CONFIGS)
        _catalog_path = None
        _catalog_revision = "python_fallback"
        _catalog_content_hash = ""
    else:
        configs = load_tier_configs_from_json(resolved)
        _catalog = ModelCatalog(configs)
        _catalog_path = resolved.resolve()
        meta_raw = json.loads(resolved.read_text(errors="replace")).get("meta") or {}
        _catalog_revision = str(meta_raw.get("revision", "unknown"))
        _catalog_content_hash = _compute_content_hash(resolved)
    MODEL_CATALOG._replace(_catalog)
    TIER_CONFIGS.clear()
    TIER_CONFIGS.update({cfg.backend: cfg for cfg in _catalog.configs})
    return _catalog


def get_catalog() -> ModelCatalog:
    """Return the current module-level catalog, initializing from Python defaults if needed."""
    global _catalog
    if _catalog is None:
        _catalog = ModelCatalog(DEFAULT_TIER_CONFIGS)
    return _catalog


def catalog_revision() -> str:
    """Return the revision string of the loaded catalog."""
    return _catalog_revision


def catalog_path() -> Path | None:
    """Return the path of the loaded catalog, or None if using Python fallback."""
    return _catalog_path


def catalog_source_info() -> dict:
    """Return catalog provenance for writing to run records."""
    return {
        "catalog_path": str(catalog_path()) if catalog_path() else "python_fallback",
        "catalog_revision": catalog_revision(),
        "catalog_content_hash": _catalog_content_hash,
    }


class _CatalogHandle:
    """Mutable handle that delegates to the current ModelCatalog.

    ``from .model_tiers import MODEL_CATALOG`` captures this handle at import
    time.  When ``init_catalog()`` replaces the underlying catalog the same
    handle transparently delegates to the new instance — no import-site changes
    needed.
    """

    __slots__ = ("_catalog",)

    def __init__(self, catalog: ModelCatalog) -> None:
        object.__setattr__(self, "_catalog", catalog)

    def _replace(self, catalog: ModelCatalog) -> None:
        object.__setattr__(self, "_catalog", catalog)

    def __getattr__(self, name: str):
        return getattr(self._catalog, name)

    def __repr__(self) -> str:
        return repr(self._catalog)


# Module-level catalog: start from Python defaults, then try JSON.
_catalog = ModelCatalog(DEFAULT_TIER_CONFIGS)
MODEL_CATALOG = _CatalogHandle(_catalog)
TIER_CONFIGS: dict[str, TierConfig] = {cfg.backend: cfg for cfg in _catalog.configs}


def _load_default_json_catalog() -> None:
    """Try loading the default JSON catalog; non-fatal if missing."""
    global _catalog, _catalog_path, _catalog_revision, _catalog_content_hash
    default = DEFAULT_CATALOG_PATH
    if not default.is_file():
        return
    try:
        configs = load_tier_configs_from_json(default)
        _catalog = ModelCatalog(configs)
        _catalog_path = default.resolve()
        meta_raw = json.loads(default.read_text(errors="replace")).get("meta") or {}
        _catalog_revision = str(meta_raw.get("revision", "unknown"))
        _catalog_content_hash = _compute_content_hash(default)
        MODEL_CATALOG._replace(_catalog)
        TIER_CONFIGS.clear()
        TIER_CONFIGS.update({cfg.backend: cfg for cfg in _catalog.configs})
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        pass


_load_default_json_catalog()


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
