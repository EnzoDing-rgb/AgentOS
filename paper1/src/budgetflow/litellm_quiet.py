"""Silence litellm provider-detection noise (red 'Provider List' spam)."""

from __future__ import annotations

import logging
import os


def configure_litellm_quiet() -> None:
    os.environ.setdefault("LITELLM_LOG", "ERROR")
    for name in ("LiteLLM", "litellm", "LiteLLM Proxy"):
        logging.getLogger(name).setLevel(logging.ERROR)
    try:
        import litellm

        litellm.set_verbose = False
        litellm.suppress_debug_info = True
        turn_off = getattr(litellm, "turn_off_message_logging", None)
        if callable(turn_off):
            turn_off()
    except ImportError:
        pass
