"""ANSI console helpers for live run monitoring (heartbeat / trace / runner)."""

from __future__ import annotations

import os
import sys

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"

# fg
_BLACK = "\033[30m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"
_WHITE = "\033[37m"

# bright fg
_BRIGHT_RED = "\033[91m"
_BRIGHT_GREEN = "\033[92m"
_BRIGHT_YELLOW = "\033[93m"
_BRIGHT_BLUE = "\033[94m"
_BRIGHT_MAGENTA = "\033[95m"
_BRIGHT_CYAN = "\033[96m"

PHASE_COLORS: dict[str, str] = {
    "explore": _BLUE,
    "edit_gold": _BRIGHT_GREEN,
    "edit_target": _BRIGHT_GREEN,
    "edit_related": _YELLOW,
    "edit_other": _BRIGHT_YELLOW,
    "patch_prep": _YELLOW,
    "test": _MAGENTA,
    "submit": _CYAN,
    "prep": _BRIGHT_CYAN,
    "agent": _CYAN,
}

ROUTING_STAGE_COLORS: dict[str, str] = {
    "localization": _BLUE,
    "repair": _BRIGHT_GREEN,
    "validation": _MAGENTA,
}

BACKEND_TIER_COLORS: dict[str, str] = {
    "tier1": _BRIGHT_CYAN,
    "tier2": _BRIGHT_YELLOW,
    "tier3": _BRIGHT_MAGENTA,
}


def color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def paint(text: str, *styles: str) -> str:
    if not color_enabled() or not styles:
        return text
    return "".join(styles) + text + _RESET


def tag(label: str, *, color: str = _CYAN, bold: bool = True) -> str:
    if bold:
        styles = (color, _BOLD)
    else:
        styles = (_DIM,)
    return paint(f"[{label}]", *styles)


def bold(text: str) -> str:
    return paint(text, _BOLD)


def status_pass(text: str = "PASS") -> str:
    return paint(text, _BRIGHT_GREEN, _BOLD)


def status_fail(text: str = "FAIL") -> str:
    return paint(text, _BRIGHT_RED, _BOLD)


def status_yes(text: str = "YES") -> str:
    return paint(text, _BRIGHT_GREEN, _BOLD)


def status_no(text: str = "NO") -> str:
    return paint(text, _BRIGHT_YELLOW, _BOLD)


def harness_stage(stage: str, value: str | None) -> str:
    if not value:
        return status_pending("?")
    lowered = value.lower()
    if stage == "fail_before":
        return status_pass("OK") if lowered == "fail" else status_fail("BAD")
    if stage in {"test_patch", "model_patch"}:
        return status_pass("OK") if lowered == "ok" else status_fail("FAIL")
    if stage in {"fail_after", "pass_to_pass"}:
        return status_pass("OK") if lowered == "pass" else status_fail("FAIL")
    if lowered in {"ok", "pass", "yes"}:
        return status_pass("OK")
    if lowered.startswith("fail") or lowered in {"no", "error"}:
        return status_fail("FAIL")
    return status_pending(value[:12])


def status_pending(text: str = "pending") -> str:
    return text


def phase_label(phase: str) -> str:
    color = PHASE_COLORS.get(phase, _WHITE)
    return paint(phase, color, _BOLD)


def routing_stage_label(stage: str) -> str:
    key = (stage or "").lower().replace("stage.", "")
    color = ROUTING_STAGE_COLORS.get(key, _WHITE)
    short = {"localization": "LOC", "repair": "REP", "validation": "VAL"}.get(key, key.upper()[:3] or "?")
    return paint(short, color, _BOLD)


def backend_tier_label(backend_name: str) -> str:
    if not backend_name or backend_name == "-":
        return dim("-")
    lowered = backend_name.lower()
    if "tier1" in lowered or "spark" in lowered:
        tier, label = "tier1", "T1/codex-spark"
    elif "tier2" in lowered or "gpt54" in lowered or "mini" in lowered:
        tier, label = "tier2", "T2/gpt-5.4-mini"
    elif "tier3" in lowered or "codex" in lowered:
        tier, label = "tier3", "T3/gpt-5.3-codex"
    else:
        return paint(backend_name, _DIM)
    return paint(label, BACKEND_TIER_COLORS[tier], _BOLD)


def warn_label(text: str) -> str:
    return paint(text, _BRIGHT_RED, _BOLD)


def ok_label(text: str) -> str:
    return paint(text, _BRIGHT_GREEN, _BOLD)


def fail_label(text: str) -> str:
    return paint(text, _BRIGHT_RED, _BOLD)


def dim(text: str) -> str:
    return paint(text, _DIM)


def format_tier_pool_line() -> str:
    """One-line tier → model_id summary for run banners."""
    from .defaults import TIER1_MODEL, TIER2_MODEL, TIER3_MODEL

    return (
        f"T1={dim(TIER1_MODEL)}  "
        f"T2={dim(TIER2_MODEL)}  "
        f"T3={bold(TIER3_MODEL)}"
    )


def parse_harness_detail(detail: str) -> dict[str, str]:
    stages: dict[str, str] = {}
    for part in detail.split(";"):
        chunk = part.strip()
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        stages[key.strip()] = value.strip()
    return stages


def format_harness_board(detail: str) -> str:
    stages = parse_harness_detail(detail)
    parts = [
        f"test_patch={harness_stage('test_patch', stages.get('test_patch'))}",
        f"fail_before={harness_stage('fail_before', stages.get('fail_before'))}",
        f"model_patch={harness_stage('model_patch', stages.get('model_patch'))}",
        f"fail_after={harness_stage('fail_after', stages.get('fail_after'))}",
        f"pass_to_pass={harness_stage('pass_to_pass', stages.get('pass_to_pass'))}",
    ]
    return " ".join(parts)


def format_run_verdict(
    *,
    harness_resolved: bool,
    patch_extracted: bool,
    gold_edited: bool,
    gold_file: str = "-",
    detail: str = "",
) -> str:
    if not patch_extracted:
        verdict = status_fail("NO PATCH")
    elif harness_resolved:
        verdict = status_pass("PATCH PASSED HARNESS")
    else:
        verdict = status_fail("PATCH FAILED HARNESS")
    gold = status_yes(gold_file) if gold_edited else status_no("none")
    return f"verdict={verdict} | gold={gold} | {format_harness_board(detail)}"
