"""Structured run tracing: per-step jsonl + heartbeat progress signals."""

from __future__ import annotations

import json
import subprocess
import time
from collections import deque
from pathlib import Path
from typing import Literal

from minisweagent.agents.default import DefaultAgent

from .console_log import (
    bold,
    dim,
    format_harness_board,
    format_run_verdict,
    status_fail,
    status_no,
    status_pass,
    status_pending,
    status_yes,
    tag,
)

TraceConsoleLevel = Literal["quiet", "milestones", "verbose"]


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
        ignore_changed_files: tuple[str, ...] = (),
        console_level: TraceConsoleLevel = "quiet",
        progress_box: dict[str, str] | None = None,
    ) -> None:
        self.instance_id = instance_id
        self.repo_dir = repo_dir
        self.trace_dir = trace_dir
        self.target_files = tuple(target_files)
        self.strategy_label = strategy_label or "unknown"
        self.ignore_changed_files = frozenset(ignore_changed_files)
        self.console_level = console_level
        self._progress_box = progress_box
        self.steps_path = trace_dir / "steps.jsonl"
        self._recent_commands: deque[str] = deque(maxlen=8)
        self._last_changed: list[str] = []
        self._gold_files_edited: set[str] = set()
        self._steps_logged = 0
        self._submitted = False
        self._last_agent_pytest: str | None = None
        self._harness_resolved: bool | None = None
        self._last_printed_phase: str | None = None
        self._gold_milestone_printed = False
        self._submit_milestone_printed = False
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

    def _update_agent_pytest(self, commands: list[str], observation: dict) -> str | None:
        if not commands or not observation:
            return None
        last_cmd = commands[-1]
        if not _is_pytest_command(last_cmd):
            return None
        rc = observation.get("returncode", "")
        prev = self._last_agent_pytest
        if rc == "0":
            self._last_agent_pytest = "pass"
        elif rc:
            self._last_agent_pytest = "fail"
        if self._last_agent_pytest != prev:
            return self._last_agent_pytest
        return None

    def _agent_state(self, *, step: int, phase: str, gold_edited: list[str]) -> dict[str, object]:
        return {
            "step": step,
            "phase": phase,
            "gold_edited": bool(gold_edited or self._gold_files_edited),
            "gold_files": sorted(self._gold_files_edited or set(gold_edited)),
            "submitted": self._submitted,
            "agent_pytest": self._last_agent_pytest,
        }

    def compact_status(self, agent: DefaultAgent, *, elapsed_s: float) -> str:
        changed = self._last_changed or git_changed_files(self.repo_dir, timeout_s=3)
        agent_changed = [f for f in changed if f not in self.ignore_changed_files]
        gold_edited = [f for f in agent_changed if f in self.target_files]
        phase = self._classify_phase(commands=[], changed=agent_changed, gold_edited=gold_edited)
        gold = status_yes() if (gold_edited or self._gold_files_edited) else status_no()
        submitted = status_yes() if self._submitted else status_no()
        agent_test = _format_agent_pytest(self._last_agent_pytest)
        if self._harness_resolved is None:
            harness = status_pending("pending")
        elif self._harness_resolved:
            harness = status_pass("PASS")
        else:
            harness = status_fail("FAIL")
        gold_files = ",".join(sorted(self._gold_files_edited)[:1]) or "-"
        return (
            f"step={agent.n_calls} phase={phase} "
            f"gold={gold} file={dim(gold_files)} submit={submitted} "
            f"agent_test={agent_test} harness={harness} elapsed={elapsed_s:.0f}s"
        )

    def _status_board(self, *, step: int, phase: str, gold_edited: list[str]) -> str:
        gold = status_yes() if gold_edited else status_no()
        submitted = status_yes() if self._submitted else status_no()
        agent_test = _format_agent_pytest(self._last_agent_pytest)
        if self._harness_resolved is None:
            harness = status_pending("pending")
        elif self._harness_resolved:
            harness = status_pass("PASS")
        else:
            harness = status_fail("FAIL")
        return (
            f"step={step} phase={phase} | "
            f"gold_edit={gold} agent_pytest={agent_test} submitted={submitted} harness={harness}"
        )

    def _detect_submitted(self, commands: list[str]) -> None:
        for cmd in commands:
            lowered = cmd.lower()
            if "complete_task" in lowered:
                self._submitted = True
                return
            if "patch.txt" in lowered or "git diff" in lowered:
                self._submitted = True
                return

    def finalize_agent(self, *, submitted: bool, patch_extracted: bool) -> None:
        if submitted or patch_extracted:
            self._submitted = True

    def _print_milestones(
        self,
        *,
        phase: str,
        gold_edited: list[str],
        pytest_changed: str | None,
    ) -> None:
        if gold_edited and not self._gold_milestone_printed:
            self._gold_milestone_printed = True
            files = ", ".join(gold_edited[:2])
            print(
                f"{tag('agent', bold=False)} {self.instance_id} {self.strategy_label} "
                f"patched gold file: {bold(files)}",
                flush=True,
            )
        if phase == "submit" and not self._submit_milestone_printed:
            self._submit_milestone_printed = True
            print(
                f"{tag('agent', bold=False)} {self.instance_id} {self.strategy_label} "
                f"submitting patch...",
                flush=True,
            )
        if pytest_changed:
            label = status_pass("PASS") if pytest_changed == "pass" else status_fail("FAIL")
            print(
                f"{tag('agent', bold=False)} {self.instance_id} {self.strategy_label} "
                f"agent pytest {label}",
                flush=True,
            )

    def _should_print_step(self, *, phase: str, gold_edited: list[str], pytest_changed: str | None) -> bool:
        if self.console_level == "verbose":
            return True
        if self.console_level == "quiet":
            return False
        if pytest_changed:
            return True
        if gold_edited and not self._gold_files_edited:
            return True
        if phase in {"submit", "test"} and phase != self._last_printed_phase:
            return True
        return False

    def _publish_progress(self, agent: DefaultAgent, *, elapsed_s: float) -> None:
        if self._progress_box is not None:
            self._progress_box["status"] = self.compact_status(agent, elapsed_s=elapsed_s)

    def log_step(self, agent: DefaultAgent, *, elapsed_s: float) -> dict:
        messages = agent.messages
        assistant = messages[-2] if len(messages) >= 2 else {}
        if assistant.get("role") != "assistant":
            assistant = next((m for m in reversed(messages) if m.get("role") == "assistant"), {})

        commands = _extract_bash_commands(assistant)
        for cmd in commands:
            self._recent_commands.append(cmd)
        self._detect_submitted(commands)
        if any("COMPLETE_TASK" in c for c in commands):
            self._submitted = True

        changed = git_changed_files(self.repo_dir)
        self._last_changed = changed
        agent_changed = [f for f in changed if f not in self.ignore_changed_files]
        gold_edited = [f for f in agent_changed if f in self.target_files]
        self._gold_files_edited.update(gold_edited)
        observation = _last_observation_summary(messages)
        pytest_changed = self._update_agent_pytest(commands, observation)
        phase = self._classify_phase(commands=commands, changed=agent_changed, gold_edited=gold_edited)

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
            "changed_files": agent_changed[:12],
            "compat_baseline_files": sorted(self.ignore_changed_files),
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

        self._publish_progress(agent, elapsed_s=elapsed_s)
        self._print_milestones(phase=phase, gold_edited=gold_edited, pytest_changed=pytest_changed)
        if self._should_print_step(phase=phase, gold_edited=gold_edited, pytest_changed=pytest_changed):
            line = self._status_board(step=agent.n_calls, phase=phase, gold_edited=gold_edited)
            print(f"{tag('trace', bold=False)} {self.instance_id} {line}", flush=True)
            self._last_printed_phase = phase
        return record

    def log_harness_result(
        self,
        *,
        resolved: bool,
        detail: str,
        patch_extracted: bool = True,
    ) -> None:
        self._harness_resolved = resolved
        gold_file = next(iter(self._gold_files_edited), "-")
        verdict = format_run_verdict(
            harness_resolved=resolved,
            patch_extracted=patch_extracted,
            gold_edited=bool(self._gold_files_edited),
            gold_file=gold_file,
            detail=detail,
        )
        print(f"{tag('verdict', bold=False)} {self.instance_id} {self.strategy_label} {verdict}", flush=True)
        if not resolved:
            fail_reason = ""
            for part in detail.split(";"):
                chunk = part.strip()
                if chunk.startswith(("fail_after=", "pass_to_pass=", "model_patch=")) and "fail" in chunk.lower():
                    fail_reason = chunk.split("=", 1)[1].strip()[:160]
                    break
            if fail_reason:
                print(f"  cause: {dim(fail_reason)}", flush=True)

    def heartbeat_status(self, agent: DefaultAgent, *, elapsed_s: float) -> str:
        return self.compact_status(agent, elapsed_s=elapsed_s)

    def agent_summary(self) -> dict[str, object]:
        return {
            "gold_edited": bool(self._gold_files_edited),
            "gold_files": sorted(self._gold_files_edited),
            "submitted": self._submitted,
            "agent_pytest": self._last_agent_pytest,
        }


class TracedDefaultAgent(DefaultAgent):
    def __init__(self, *args, trace: RunTraceLogger, run_started: float, **kwargs):
        super().__init__(*args, **kwargs)
        self._trace = trace
        self._run_started = run_started

    def step(self) -> list[dict]:
        result = super().step()
        self._trace.log_step(self, elapsed_s=time.time() - self._run_started)
        return result
