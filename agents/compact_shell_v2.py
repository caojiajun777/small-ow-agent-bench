"""SmallOWBench 2 lightweight agent; no legacy protocol or shell-state changes.

Rules/task are the first USER message, not a system-role message. Every action
runs a new bash process in /app. Only finalization performs an extra sandbox
call, to archive bounded data artifacts; this call is never model feedback.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import shlex
import time
from pathlib import Path
from typing import Any

from harbor.agents.base import BaseAgent
from harbor.llms.base import ContextLengthExceededError, OutputLengthExceededError
from harbor.llms.chat import Chat
from harbor.llms.lite_llm import LiteLLM

from agents.artifacts_v2 import (
    CaptureLimits, artifact_policy, capture_script, save_capture, validate_capture,
    write_atomic, write_json_atomic,
)
from agents.protocol_v2 import (
    HARNESS_VERSION, PARSE_FAIL_OBSERVATION, SYSTEM_PROMPT, format_observation, parse_action,
)


class CompactShellV2Agent(BaseAgent):
    SUPPORTS_ATIF = False
    SUPPORTS_WINDOWS = False

    def __init__(self, logs_dir: Path, task_id: str, model_name: str | None = None,
                 max_turns: int = 20, command_timeout_sec: float = 60,
                 observation_limit: int = 8000, temperature: float = 0.0,
                 llm_call_kwargs: dict[str, Any] | None = None,
                 protocol_clarification: str | None = None,
                 artifact_timeout_sec: float = 15,
                 artifact_max_files: int = 256,
                 artifact_max_file_bytes: int = 1_048_576,
                 artifact_max_total_bytes: int = 8_388_608,
                 version_label: str | None = None,
                 extra_env: dict[str, str] | None = None, *args, **kwargs):
        artifact_policy(task_id)
        if version_label not in (None, HARNESS_VERSION):
            raise ValueError("version_label must match the actual harness version")
        if type(max_turns) is not int or max_turns < 1 or type(observation_limit) is not int or observation_limit < 1:
            raise ValueError("turn and observation limits must be positive integers")
        if command_timeout_sec <= 0 or artifact_timeout_sec <= 0:
            raise ValueError("timeouts must be positive")
        super().__init__(logs_dir=logs_dir, model_name=model_name, extra_env=extra_env, *args, **kwargs)
        self._task_id = task_id
        self._max_turns = max_turns
        self._command_timeout_sec = command_timeout_sec
        self._observation_limit = observation_limit
        self._temperature = temperature
        self._llm_call_kwargs = dict(llm_call_kwargs or {})
        self._clarification = protocol_clarification
        self._artifact_timeout_sec = artifact_timeout_sec
        self._capture_limits = CaptureLimits(artifact_max_files, artifact_max_file_bytes, artifact_max_total_bytes)
        self._trace = {}
        self._chat = None

    @staticmethod
    def name() -> str:
        return "compact-shell-v2"

    def version(self) -> str:
        return HARNESS_VERSION

    async def setup(self, environment) -> None:
        return None

    def _checkpoint(self, context) -> None:
        trace = self._trace
        trace["n_turns"] = len(trace["turns"])
        if self._chat is not None:
            context.n_input_tokens = self._chat.total_input_tokens
            context.n_output_tokens = self._chat.total_output_tokens
            context.n_cache_tokens = self._chat.total_cache_tokens
            context.cost_usd = self._chat.total_cost
        trace["usage"] = {"input_tokens": context.n_input_tokens, "output_tokens": context.n_output_tokens,
                          "cache_tokens": context.n_cache_tokens, "cost_usd": context.cost_usd,
                          "scope": "completed Chat responses only; failed/truncated request billing may be unavailable"}
        context.metadata = {key: trace.get(key) for key in (
            "harness_version", "version", "task_id", "finished", "n_turns", "n_shell", "n_shell_attempts",
            "n_parse_fail", "termination_reason", "artifact_capture_status", "artifact_manifest_path",
            "artifact_manifest_sha256",
        )}
        write_json_atomic(self.logs_dir / "compact-shell-v2.json", trace)

    def _start_call(self, kind: str, turn: int) -> dict:
        call = {"kind": kind, "turn": turn, "status": "running", "started_monotonic": time.monotonic()}
        self._trace["calls"].append(call)
        return call

    @staticmethod
    def _end_call(call: dict, status: str, error: BaseException | None = None) -> None:
        call["status"] = status
        call["elapsed_seconds"] = max(0.0, time.monotonic() - call["started_monotonic"])
        if error is not None:
            call["error_type"] = type(error).__name__

    async def _archive(self, environment, context) -> None:
        start = time.monotonic()
        self._trace["artifact_capture_status"] = "error"
        self._trace["artifact_manifest_path"] = "artifacts/manifest.json"
        self._checkpoint(context)
        manifest = None
        decoded = {}
        try:
            command = "python3 -I -B -c " + shlex.quote(capture_script(self._task_id, self._capture_limits))
            result = await asyncio.wait_for(
                environment.exec(command, cwd="/app", timeout_sec=self._artifact_timeout_sec),
                timeout=self._artifact_timeout_sec,
            )
            if result.return_code != 0:
                raise ValueError("artifact capture command failed")
            manifest, decoded = validate_capture(json.loads(result.stdout or ""), self._task_id, self._capture_limits)
        except BaseException as exc:
            # Capture is diagnostic; never replace an already determined model result.
            # A second cancellation also cannot produce a false complete manifest.
            if not isinstance(exc, (Exception, asyncio.CancelledError)):
                raise
            manifest = {"schema_version": 2, "harness_version": HARNESS_VERSION, "task_id": self._task_id,
                        "status": "error", "files": [], "missing": artifact_policy(self._task_id)["required"],
                        "issues": [{"path": "", "reason": "capture_error", "error_type": type(exc).__name__}],
                        "atomic": False, "final_state_verified": False, "limits": self._capture_limits.__dict__,
                        "total_bytes": 0}
        manifest["capture_elapsed_seconds"] = max(0.0, time.monotonic() - start)
        manifest["termination_reason"] = self._trace["termination_reason"]
        manifest["capture_phase"] = "after_model_loop"
        # Even a successful copy is not proof that detached processes stopped writing.
        manifest["final_state_verified"] = False
        try:
            sha = save_capture(self.logs_dir / "artifacts", manifest, decoded)
        except Exception as exc:
            manifest = {"schema_version": 2, "harness_version": HARNESS_VERSION, "task_id": self._task_id,
                        "status": "error", "files": [], "missing": artifact_policy(self._task_id)["required"],
                        "issues": [{"path": "", "reason": "archive_write_error", "error_type": type(exc).__name__}],
                        "atomic": False, "final_state_verified": False, "termination_reason": self._trace["termination_reason"],
                        "capture_elapsed_seconds": max(0.0, time.monotonic() - start),
                        "limits": self._capture_limits.__dict__, "total_bytes": 0}
            sha = write_json_atomic(self.logs_dir / "artifacts" / "manifest.json", manifest)
        self._trace["artifact_capture_status"] = manifest["status"]
        self._trace["artifact_manifest_sha256"] = sha
        self._trace["artifact_capture_elapsed_seconds"] = manifest["capture_elapsed_seconds"]

    async def run(self, instruction, environment, context) -> None:
        if not self.model_name:
            raise ValueError("compact-shell-v2 requires a model")
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._trace = {
            "schema_version": 2, "harness_version": HARNESS_VERSION, "version": HARNESS_VERSION,
            "task_id": self._task_id, "finished": False, "n_turns": 0, "n_shell": 0, "n_shell_attempts": 0,
            "n_parse_fail": 0, "termination_reason": "running", "turns": [], "calls": [],
            "artifact_capture_status": "not_attempted", "artifact_manifest_path": None,
            "artifact_manifest_sha256": None,
            "runtime_contract": {"initial_message_role": "user", "shell": "independent bash -c", "cwd": "/app",
                                 "shell_state_persists": False, "max_turns": self._max_turns,
                                 "command_timeout_sec": self._command_timeout_sec, "observation_limit_chars": self._observation_limit,
                                 "llm_budget_policy": "output/context exhaustion ends the episode; truncated responses never execute",
                                 "artifact_capture": "one bounded post-loop sandbox call; never model feedback",
                                 "artifact_timeout_sec": self._artifact_timeout_sec},
        }
        self._chat = None
        pending_error = None
        phase = "initialization"
        active_call = None
        started = time.monotonic()
        try:
            self._checkpoint(context)
            self._chat = Chat(LiteLLM(model_name=self.model_name, temperature=self._temperature))
            rules = SYSTEM_PROMPT + (("\n# Declared protocol clarification\n" + self._clarification.strip()) if self._clarification else "")
            prompt = rules + "\n# Task\n" + instruction.strip() + "\n"
            self._trace["initial_prompt_sha256"] = hashlib.sha256(prompt.encode()).hexdigest()
            for turn in range(1, self._max_turns + 1):
                phase = "api"
                active_call = self._start_call("api", turn)
                active_call.update(prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(), response_log_path=f"turn-{turn}.txt")
                self._checkpoint(context)
                try:
                    response = await self._chat.chat(prompt, logging_path=self.logs_dir / f"turn-{turn}.txt", **self._llm_call_kwargs)
                except (OutputLengthExceededError, ContextLengthExceededError) as exc:
                    # These typed backend signals are episode budget outcomes,
                    # not upstream failures to retry. Never parse a partial
                    # response: even a closed action fence may precede truncation.
                    reason = "output_limit" if isinstance(exc, OutputLengthExceededError) else "context_limit"
                    self._end_call(active_call, "budget_exceeded", exc)
                    active_call["termination_reason"] = reason
                    truncated = getattr(exc, "truncated_response", None)
                    if isinstance(truncated, str):
                        path = f"turn-{turn}.truncated.txt"
                        data = truncated.encode("utf-8")
                        write_atomic(self.logs_dir / path, data)
                        active_call.update(truncated_response_path=path,
                                           truncated_response_sha256=hashlib.sha256(data).hexdigest(),
                                           truncated_response_chars=len(truncated))
                    self._trace.update(termination_reason=reason, exception_type=type(exc).__name__)
                    active_call = None
                    self._checkpoint(context)
                    break
                active_call["response_sha256"] = hashlib.sha256((response.content or "").encode("utf-8")).hexdigest()
                self._end_call(active_call, "completed")
                active_call = None
                action = parse_action(response.content or "")
                record = {"turn": turn, "kind": action.kind, "reason": action.reason}
                self._trace["turns"].append(record)
                if action.kind == "finish":
                    self._trace["finished"] = True
                    self._trace["termination_reason"] = "finish"
                    self._checkpoint(context)
                    break
                if action.kind == "invalid":
                    self._trace["n_parse_fail"] += 1
                    record.update(status="invalid", observation=PARSE_FAIL_OBSERVATION)
                    prompt = PARSE_FAIL_OBSERVATION
                    self._checkpoint(context)
                    continue
                phase = "command"
                record.update(command=action.command, status="running")
                self._trace["n_shell_attempts"] += 1
                active_call = self._start_call("shell", turn)
                # A crash/cancel during exec still leaves the attempted command on disk.
                self._checkpoint(context)
                result = await asyncio.wait_for(
                    environment.exec("bash -c " + shlex.quote(action.command), cwd="/app", timeout_sec=self._command_timeout_sec),
                    timeout=self._command_timeout_sec,
                )
                self._end_call(active_call, "completed")
                active_call = None
                self._trace["n_shell"] += 1
                stdout, stderr = result.stdout or "", result.stderr or ""
                prefix = f"shell/turn-{turn:03d}"
                write_atomic(self.logs_dir / (prefix + ".stdout.txt"), stdout.encode("utf-8"))
                write_atomic(self.logs_dir / (prefix + ".stderr.txt"), stderr.encode("utf-8"))
                observation = format_observation(stdout, stderr, result.return_code, self._observation_limit)
                record.update(status="completed", raw_output_status="complete", return_code=result.return_code, observation=observation.text,
                              observation_metadata=observation.metadata(), stdout_path=prefix + ".stdout.txt",
                              stderr_path=prefix + ".stderr.txt", stdout_sha256=hashlib.sha256(stdout.encode()).hexdigest(),
                              stderr_sha256=hashlib.sha256(stderr.encode()).hexdigest())
                prompt = observation.text
                self._checkpoint(context)
            else:
                self._trace["termination_reason"] = "max_turns"
        except BaseException as exc:
            if not isinstance(exc, (Exception, asyncio.CancelledError)):
                raise
            pending_error = exc
            if active_call is not None:
                self._end_call(active_call, "cancelled" if isinstance(exc, asyncio.CancelledError) else "error", exc)
            if isinstance(exc, asyncio.CancelledError):
                reason = "cancelled"
            elif phase == "api":
                reason = "api_error"
            elif phase == "command" and (isinstance(exc, TimeoutError) or type(exc).__name__ in {"CommandTimeoutError", "CommandTimeoutException"}):
                reason = "command_timeout"
            elif phase == "command":
                reason = "command_error"
            else:
                reason = "internal_error"
            self._trace.update(termination_reason=reason, exception_type=type(exc).__name__)
            if phase == "command" and self._trace["turns"]:
                self._trace["turns"][-1]["status"] = reason
                self._trace["turns"][-1]["raw_output_status"] = "unavailable_no_exec_result"
        finally:
            self._trace["model_loop_elapsed_seconds"] = max(0.0, time.monotonic() - started)
            try:
                self._checkpoint(context)
            except Exception as exc:
                self._trace.setdefault("finalization_errors", []).append({"stage": "pre_capture_checkpoint", "error_type": type(exc).__name__})
            try:
                await self._archive(environment, context)
            except (Exception, asyncio.CancelledError) as exc:
                self._trace["artifact_capture_status"] = "error"
                self._trace.setdefault("finalization_errors", []).append({"stage": "artifact_finalization", "error_type": type(exc).__name__})
            finally:
                self._trace["total_elapsed_seconds"] = max(0.0, time.monotonic() - started)
                try:
                    self._checkpoint(context)
                except Exception as exc:
                    self._trace.setdefault("finalization_errors", []).append({"stage": "final_checkpoint", "error_type": type(exc).__name__})
        if pending_error is not None:
            raise pending_error
