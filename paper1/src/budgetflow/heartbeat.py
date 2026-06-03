from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from .console_log import tag


def run_with_heartbeat(
    label: str,
    fn: Callable[[], Any],
    *,
    interval_s: float = 30.0,
    status_fn: Callable[[], str] | None = None,
    on_beat: Callable[[], None] | None = None,
) -> Any:
    """Run blocking fn; print heartbeat every interval_s until fn returns.

    If *on_beat* is given, it is called after every heartbeat print (useful
    for updating a heartbeat file so external checkers see liveness).
    """
    stop = threading.Event()
    started = time.time()

    def _loop() -> None:
        while not stop.wait(interval_s):
            elapsed = time.time() - started
            extra = status_fn() if status_fn else ""
            line = f"{tag('heartbeat', bold=False)} {label} elapsed={elapsed:.0f}s"
            if extra:
                line += f" | {extra}"
            print(line, flush=True)
            if on_beat is not None:
                try:
                    on_beat()
                except Exception:
                    pass

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    try:
        return fn()
    finally:
        stop.set()
        thread.join(timeout=1.0)
