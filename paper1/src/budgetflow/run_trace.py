"""Structured run tracing: per-step jsonl + heartbeat progress signals."""

from __future__ import annotations

import json
import subprocess
import time
from collections import deque
from pathlib import Path

from minisweagent.agents.default import DefaultAgent

from .console_log import dim, fail_label, ok_label, paint, phase_label, tag, warn_label


def patch_local_swebench_config(config: dict, repo_dir: Path) -> dict:
    """Map Docker /testbed paths to the real local checkout."""
    repo = str(repo_dir)
    agent = config.setdefault("agent", {})
    for key in ("system_template", "instance_template"):
        if key in agent and isinstance(agent[key], str):
            agent[key] = agent[key].replace("/testbed", repo)
    config.setdefault("environment", {})["environment_class"] = (
        config.get("environment", {}).get("environment_class")
        or "minisweagent.environments.local.LocalEnvironment"
    )
    config["environment"]["cwd"] = repo
    return config


def _extract_bash_commands(message: dict) -> list[str]:
    commands: list[str] = []
    for action in message.get("extra", {}).get("actions", []) or []:
        cmd = action.get("command")
        if cmd:
            commands.append(cmd.strip())
    return commands


def _last_observation_summary(messages: list[dict]) -> dict:
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content") or ""
        if "<returncode>" not in content:
            continue
        rc = ""
        if "<returncode>" in content:
            start = content.find("<returncode>") + len("<returncode>")
            end = content.find("</returncode>", start)
            if end > start:
                rc = content[start:end].strip()
        preview = content.replace("\n", " ")[:200]
        return {"returncode": rc, "observation_preview": preview}
    return {}


def git_changed_files(repo_dir: Path, *, timeout_s: int = 8) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.TimeoutExpired, OSError):
        return []


class RunTraceLogger:
    def __init__(
        self,
        *,
        instance_id: str,
        repo_dir: Path,
        trace_dir: Path,
        target_files: tuple[str, ...] = (),
    ) -> None:
        self.instance_id = instance_id
        self.repo_dir = repo_dir
        self.trace_dir = trace_dir
        self.target_files = tuple(target_files)
        self.steps_path = trace_dir / "steps.jsonl"
        self._recent_commands: deque[str] = deque(maxlen=8)
        self._last_changed: list[str] = []
        self._steps_logged = 0
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.steps_path.write_text("")

    def log_step(self, agent: DefaultAgent, *, elapsed_s: float) -> dict:
        messages = agent.messages
        assistant = messages[-2] if len(messages) >= 2 else {}
        if assistant.get("role") != "assistant":
            assistant = next((m for m in reversed(messages) if m.get("role") == "assistant"), {})

        commands = _extract_bash_commands(assistant)
        for cmd in commands:
            self._recent_commands.append(cmd)

        changed = git_changed_files(self.repo_dir)
        self._last_changed = changed
        hit_target = [f for f in changed if f in self.target_files]
        touched_power = any("power.py" in f for f in changed)

        repeat_score = 0
        if len(self._recent_commands) >= 2:
            last = self._recent_commands[-1]
            repeat_score = sum(1 for c in list(self._recent_commands)[:-1] if c == last)

        if hit_target:
            phase = "edit_target"
        elif touched_power:
            phase = "edit_related"
        elif any(c.startswith(("pytest", "python -m pytest", "python -c")) for c in commands):
            phase = "test"
        elif any("COMPLETE_TASK" in c or "patch.txt" in c for c in commands):
            phase = "submit"
        elif changed:
            phase = "edit_other"
        else:
            phase = "explore"

        record = {
            "ts": time.time(),
            "step": agent.n_calls,
            "elapsed_s": round(elapsed_s, 1),
            "phase": phase,
            "commands": commands[:6],
            "changed_files": changed[:12],
            "hit_target_files": hit_target,
            "target_files": list(self.target_files),
            "repeat_last_cmd": repeat_score,
            "observation": _last_observation_summary(messages),
        }
        with self.steps_path.open("a") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._steps_logged += 1

        line = (
            f"step={paint(str(agent.n_calls), '\033[1m', '\033[97m')} "
            f"phase={phase_label(phase)} "
            f"changed={paint(str(len(changed)), '\033[93m')} "
            f"hit_target={ok_label('YES') if hit_target else dim('no')}"
            f" repeat={repeat_score}"
        )
        if commands:
            cmd = commands[-1][:100]
            line += f" cmd={dim(repr(cmd))}"
        if changed:
            files = ",".join(changed[:3])
            if hit_target:
                line += f" files={ok_label(files)}"
            elif phase == "edit_other":
                line += f" files={warn_label(files)}"
            else:
                line += f" files={paint(files, '\033[93m')}"
        header = tag("trace") + " " + paint(self.instance_id, "\033[1m", "\033[96m")
        print(f"{header} {line}", flush=True)
        return record

    def heartbeat_status(self, agent: DefaultAgent, *, elapsed_s: float) -> str:
        changed = self._last_changed or git_changed_files(self.repo_dir, timeout_s=3)
        hit = [f for f in changed if f in self.target_files]
        repeat = 0
        if self._recent_commands:
            last = self._recent_commands[-1]
            repeat = sum(1 for c in self._recent_commands if c == last)
        phase = self._last_phase(changed, hit)
        parts = [
            f"llm_turns={paint(str(agent.n_calls), '\033[1m', '\033[97m')}",
            f"phase={phase_label(phase)}",
            f"changed={paint(','.join(changed[:2]) or '-', '\033[93m')}",
            f"hit_target={ok_label('YES') if hit else dim('no')}",
        ]
        if repeat >= 3 and not hit:
            parts.append(warn_label("STUCK?"))
        if changed and not hit and self.target_files:
            parts.append(warn_label("OFF_TARGET"))
        return " ".join(parts)

    def _last_phase(self, changed: list[str], hit: list[str]) -> str:
        if hit:
            return "edit_target"
        if any("power.py" in f for f in changed):
            return "edit_related"
        if changed:
            return "edit_other"
        return "explore"


class TracedDefaultAgent(DefaultAgent):
    def __init__(self, *args, trace: RunTraceLogger, run_started: float, **kwargs):
        super().__init__(*args, **kwargs)
        self._trace = trace
        self._run_started = run_started

    def step(self) -> list[dict]:
        result = super().step()
        self._trace.log_step(self, elapsed_s=time.time() - self._run_started)
        return result
