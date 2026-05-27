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
    "edit_target": _BRIGHT_GREEN,
    "edit_related": _YELLOW,
    "edit_other": _BRIGHT_YELLOW,
    "test": _MAGENTA,
    "submit": _CYAN,
    "prep": _BRIGHT_CYAN,
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
    return bold(text)


def status_fail(text: str = "FAIL") -> str:
    return bold(text)


def status_pending(text: str = "pending") -> str:
    return text


def phase_label(phase: str) -> str:
    return phase


def warn_label(text: str) -> str:
    return paint(text, _BRIGHT_RED, _BOLD)


def ok_label(text: str) -> str:
    return paint(text, _BRIGHT_GREEN, _BOLD)


def fail_label(text: str) -> str:
    return paint(text, _BRIGHT_RED, _BOLD)


def dim(text: str) -> str:
    return paint(text, _DIM)
