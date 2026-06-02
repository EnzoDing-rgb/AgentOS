from .backends import build_deepseek_backends

__all__ = ["MiniSweRunResult", "build_deepseek_backends", "run_mini_swe_task"]


def __getattr__(name: str):
    if name in {"MiniSweRunResult", "run_mini_swe_task"}:
        from .runner import MiniSweRunResult, run_mini_swe_task

        values = {
            "MiniSweRunResult": MiniSweRunResult,
            "run_mini_swe_task": run_mini_swe_task,
        }
        return values[name]
    raise AttributeError(name)
