"""Minimal DeepSeek connectivity smoke (API ping + optional 1-task agent).

Usage:
  PYTHONPATH=src:../external/mini-swe-agent/src python -u -m budgetflow.run_deepseek_smoke
  python -u -m budgetflow.run_deepseek_smoke --tier flash,pro
  python -u -m budgetflow.run_deepseek_smoke --tier t2,t3,t4,max
  python -u -m budgetflow.run_deepseek_smoke --tier pro --agent --step-limit 5
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent
MINI_SWE_SRC = REPO_ROOT.parent / "external" / "mini-swe-agent" / "src"
for path in (str(SRC), str(MINI_SWE_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

import litellm  # noqa: E402

from budgetflow.console_log import bold, dim, status_fail, status_pass, tag  # noqa: E402
from budgetflow.deepseek_backend import ensure_direct_api, load_env_file  # noqa: E402
from budgetflow.defaults import (  # noqa: E402
    DEEPSEEK_API_BASE,
    DEEPSEEK_FLASH_MODEL,
    DEEPSEEK_PRO_MODEL,
    TIER1_MODEL,
    TIER2_MODEL,
    TIER3_MODEL,
    TIER4_MODEL,
    TIER4_QWEN_MAX_MODEL,
)
from budgetflow.litellm_quiet import configure_litellm_quiet  # noqa: E402
from budgetflow.lite_tasks import load_compare_easy_tasks  # noqa: E402
from budgetflow.run_mini_swe_baseline import run_baseline_task  # noqa: E402

TIER_MODELS = {
    "t1": TIER1_MODEL,
    "qwen35": TIER1_MODEL,
    "flash": DEEPSEEK_FLASH_MODEL,
    "t2": TIER2_MODEL,
    "coder_flash": TIER2_MODEL,
    "pro": DEEPSEEK_PRO_MODEL,
    "t3": TIER3_MODEL,
    "plus": TIER3_MODEL,
    "t4": TIER4_MODEL,
    "coder_plus": TIER4_MODEL,
    "max": TIER4_QWEN_MAX_MODEL,
    "qwen_max": TIER4_QWEN_MAX_MODEL,
}
TIER_GROUPS = {
    "all": ("t1", "t2", "t3", "t4", "max"),
    "compare": ("t2", "t3", "t4"),
    "t4_candidates": ("t4", "max"),
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DeepSeek API + agent smoke")
    parser.add_argument(
        "--tier",
        type=str,
        default="flash,pro",
        help="comma list: t1,t2,t3,t4,max or aliases flash,pro,coder_plus; groups: all,compare,t4_candidates",
    )
    parser.add_argument("--agent", action="store_true", help="run 1-task mini-SWE after API ping")
    parser.add_argument("--instance-id", type=str, default="sympy__sympy-13480")
    parser.add_argument("--step-limit", type=int, default=5)
    parser.add_argument("--heartbeat", type=float, default=30.0, help="heartbeat interval during prep/agent")
    parser.add_argument(
        "--trace-verbose",
        action="store_true",
        help="print every agent step (default: milestones on gold/submit)",
    )
    return parser.parse_args()


def _expand_tiers(raw: str) -> list[str]:
    requested = [t.strip() for t in raw.split(",") if t.strip()]
    tiers: list[str] = []
    for item in requested:
        if item in TIER_GROUPS:
            tiers.extend(TIER_GROUPS[item])
        else:
            tiers.append(item)
    return tiers


def _api_ping(model: str) -> dict:
    api_key = os.environ["DEEPSEEK_API_KEY"]
    started = time.time()
    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": "Reply with exactly: pong"}],
        api_base=DEEPSEEK_API_BASE,
        api_key=api_key,
        temperature=0.0,
        max_tokens=16,
        drop_params=True,
    )
    elapsed = round(time.time() - started, 2)
    usage = getattr(response, "usage", None)
    prompt_t = getattr(usage, "prompt_tokens", 0) if usage else 0
    completion_t = getattr(usage, "completion_tokens", 0) if usage else 0
    text = (response.choices[0].message.content or "").strip()
    return {
        "ok": True,
        "model": model,
        "reply": text[:80],
        "prompt_tokens": prompt_t,
        "completion_tokens": completion_t,
        "elapsed_s": elapsed,
    }


def main() -> None:
    load_env_file()
    configure_litellm_quiet()
    ensure_direct_api()
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("DEEPSEEK_API_KEY missing in repo root .env")
    if not os.environ.get("NO_COLOR"):
        os.environ.setdefault("FORCE_COLOR", "1")

    args = _parse_args()
    tiers = _expand_tiers(args.tier)
    unknown = [t for t in tiers if t not in TIER_MODELS]
    if unknown:
        raise SystemExit(f"unknown tier {unknown}; use {sorted(TIER_MODELS)} or groups {sorted(TIER_GROUPS)}")

    print(f"{tag('smoke')} DeepSeek connectivity api_base={DEEPSEEK_API_BASE}", flush=True)

    all_ok = True
    for tier in tiers:
        model = TIER_MODELS[tier]
        print(f"\n{tag('ping', bold=False)} tier={bold(tier)} model={model}", flush=True)
        try:
            result = _api_ping(model)
            print(
                f"  {status_pass('API OK')} reply={result['reply']!r} "
                f"tokens in/out={result['prompt_tokens']}/{result['completion_tokens']} "
                f"elapsed={result['elapsed_s']}s",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            all_ok = False
            print(f"  {status_fail('API FAIL')} {type(exc).__name__}: {exc}", flush=True)

    if not all_ok:
        raise SystemExit(1)

    if not args.agent:
        print(f"\n{dim('API smoke passed. Add --agent for 1-task harness smoke (prep+heartbeat).')}", flush=True)
        return

    trace_level = "verbose" if args.trace_verbose else "milestones"
    tasks = load_compare_easy_tasks(5)
    task = next((t for t in tasks if t.instance_id == args.instance_id), tasks[0])
    for tier in tiers:
        model = TIER_MODELS[tier]
        print(
            f"\n{tag('agent', bold=False)} tier={bold(tier)} model={model} "
            f"task={task.instance_id} step_limit={args.step_limit} heartbeat={args.heartbeat}s",
            flush=True,
        )
        started = time.time()
        try:
            rec = run_baseline_task(
                task,
                step_limit=args.step_limit,
                model_name=model,
                strategy_label=f"deepseek_smoke_{tier}",
                trace_console=trace_level,
                heartbeat_s=args.heartbeat,
            )
            rec["elapsed_s"] = round(time.time() - started, 1)
            banner = status_pass("HARNESS PASS") if rec["harness_resolved"] else status_fail("HARNESS FAIL")
            print(
                f"  {banner} turns={rec.get('llm_turns')} cost={rec.get('total_cost')} "
                f"exit={rec.get('exit_status')} elapsed={rec['elapsed_s']}s",
                flush=True,
            )
            print(f"  {dim(str(rec.get('detail', ''))[:200])}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  {status_fail('AGENT FAIL')} {type(exc).__name__}: {exc}", flush=True)
            raise SystemExit(1) from exc

    print(f"\n{tag('smoke', bold=False)} all tiers passed", flush=True)


if __name__ == "__main__":
    main()
