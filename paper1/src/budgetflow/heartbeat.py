from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from .console_log import dim, ok_label, paint, tag

def run_with_heartbeat(
    label: str,
    fn: Callable[[], Any],
    *,
    interval_s: float = 30.0,
    status_fn: Callable[[], str] | None = None,
) -> Any:
    """Run blocking fn; print heartbeat every interval_s until fn returns."""
    stop = threading.Event()
    started = time.time()

    def _loop() -> None:
        while not stop.wait(interval_s):
            elapsed = time.time() - started
            extra = status_fn() if status_fn else ""
            pulse = ok_label("● ALIVE")
            header = tag("heartbeat", color="\033[96m") + " " + paint(label, "\033[1m", "\033[97m")
            elapsed_s = paint(f"{elapsed:.0f}s", "\033[93m", "\033[1m")
            line = f"{header} {pulse} elapsed={elapsed_s}"
            if extra:
                line += " " + extra
            print(line, flush=True)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    try:
        return fn()
    finally:
        stop.set()
        thread.join(timeout=1.0)
