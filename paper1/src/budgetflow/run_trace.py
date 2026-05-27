"""Structured run tracing: per-step jsonl + heartbeat progress signals."""

from __future__ import annotations

import json
import subprocess
import time
from collections import deque
from pathlib import Path

from minisweagent.agents.default import DefaultAgent

from .console_log import bold, dim, status_fail, status_pass, status_pending, tag


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
        start = content.find("<returncode>") + len("<returncode>")
        end = content.find("</returncode>", start)
        if end > start:
            rc = content[start:end].strip()
        preview = content.replace("\n", " ")[:200]
        return {"returncode": rc, "observation_preview": preview}
    return {}


def _is_pytest_command(cmd: str) -> bool:
    lowered = cmd.lower()
    return lowered.startswith("pytest") or "python -m pytest" in lowered or "pip test" in lowered


def _format_agent_pytest(last: str | None) -> str:
    if last == "pass":
        return status_pass("pass")
    if last == "fail":
        return status_fail("fail")
    return status_pending("none")


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
        strategy_label: str = "",
    ) -> None:
        self.instance_id = instance_id
        self.repo_dir = repo_dir
        self.trace_dir = trace_dir
        self.target_files = tuple(target_files)
        self.strategy_label = strategy_label or "unknown"
        self.steps_path = trace_dir / "steps.jsonl"
        self._recent_commands: deque[str] = deque(maxlen=8)
        self._last_changed: list[str] = []
        self._steps_logged = 0
        self._submitted = False
        self._last_agent_pytest: str | None = None
        self._harness_resolved: bool | None = None
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.steps_path.write_text("")

    def _classify_phase(
        self,
        *,
        commands: list[str],
        changed: list[str],
        gold_edited: list[str],
    ) -> str:
        if any("COMPLETE_TASK" in c or "patch.txt" in c for c in commands):
            return "submit"
        if any(_is_pytest_command(c) for c in commands):
            return "test"
        if gold_edited:
            return "edit_gold"
        if changed:
            return "edit_other"
        return "explore"

    def _update_agent_pytest(self, commands: list[str], observation: dict) -> None:
        if not commands or not observation:
            return
        last_cmd = commands[-1]
        if not _is_pytest_command(last_cmd):
            return
        rc = observation.get("returncode", "")
        if rc == "0":
            self._last_agent_pytest = "pass"
        elif rc:
            self._last_agent_pytest = "fail"

    def _status_board(self, *, step: int, phase: str, gold_edited: list[str]) -> str:
        gold = status_pass("yes") if gold_edited else status_pending("no")
        submitted = status_pass("yes") if self._submitted else status_pending("no")
        agent_test = _format_agent_pytest(self._last_agent_pytest)
        if self._harness_resolved is None:
            harness = status_pending("pending")
        elif self._harness_resolved:
            harness = status_pass("PASS")
        else:
            harness = status_fail("FAIL")
        return (
            f"strategy={self.strategy_label} step={step} phase={phase} | "
            f"gold_edit={gold} agent_pytest={agent_test} submitted={submitted} harness={harness}"
        )

    def log_step(self, agent: DefaultAgent, *, elapsed_s: float) -> dict:
        messages = agent.messages
        assistant = messages[-2] if len(messages) >= 2 else {}
        if assistant.get("role") != "assistant":
            assistant = next((m for m in reversed(messages) if m.get("role") == "assistant"), {})

        commands = _extract_bash_commands(assistant)
        for cmd in commands:
            self._recent_commands.append(cmd)
        if any("COMPLETE_TASK" in c for c in commands):
            self._submitted = True

        changed = git_changed_files(self.repo_dir)
        self._last_changed = changed
        gold_edited = [f for f in changed if f in self.target_files]
        observation = _last_observation_summary(messages)
        self._update_agent_pytest(commands, observation)
        phase = self._classify_phase(commands=commands, changed=changed, gold_edited=gold_edited)

        repeat_score = 0
        if len(self._recent_commands) >= 2:
            last = self._recent_commands[-1]
            repeat_score = sum(1 for c in list(self._recent_commands)[:-1] if c == last)

        record = {
            "ts": time.time(),
            "step": agent.n_calls,
            "elapsed_s": round(elapsed_s, 1),
            "strategy": self.strategy_label,
            "phase": phase,
            "commands": commands[:6],
            "changed_files": changed[:12],
            "gold_edited_files": gold_edited,
            "target_files": list(self.target_files),
            "submitted": self._submitted,
            "agent_pytest": self._last_agent_pytest,
            "harness_resolved": self._harness_resolved,
            "repeat_last_cmd": repeat_score,
            "observation": observation,
        }
        with self.steps_path.open("a") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._steps_logged += 1

        line = self._status_board(step=agent.n_calls, phase=phase, gold_edited=gold_edited)
        if commands:
            line += f" | cmd={dim(repr(commands[-1][:80]))}"
        print(f"{tag('trace', bold=False)} {self.instance_id} {line}", flush=True)
        return record

    def log_harness_result(self, *, resolved: bool, detail: str) -> None:
        self._harness_resolved = resolved
        harness = status_pass("PASS") if resolved else status_fail("FAIL")
        print(
            f"{tag('result', bold=False)} {self.instance_id} strategy={self.strategy_label} "
            f"harness={harness} detail={dim(detail[:200])}",
            flush=True,
        )

    def heartbeat_status(self, agent: DefaultAgent, *, elapsed_s: float) -> str:
        changed = self._last_changed or git_changed_files(self.repo_dir, timeout_s=3)
        gold_edited = [f for f in changed if f in self.target_files]
        phase = self._classify_phase(commands=[], changed=changed, gold_edited=gold_edited)
        return self._status_board(step=agent.n_calls, phase=phase, gold_edited=gold_edited)

    def _last_phase(self, changed: list[str], gold_edited: list[str]) -> str:
        if gold_edited:
            return "edit_gold"
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
