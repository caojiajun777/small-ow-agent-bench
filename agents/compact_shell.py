"""Minimal Harbor agent: instruction → model → bash|finish → shell.

Not Terminus-2. No JSON tools, no tmux, no summarizer, no auto-repair.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.llms.chat import Chat
from harbor.llms.lite_llm import LiteLLM
from harbor.models.agent.context import AgentContext

try:
    from agents.protocol import (
        PARSE_FAIL_OBSERVATION,
        SYSTEM_PROMPT,
        format_observation,
        parse_action,
    )
except ImportError:  # pytest / direct file load
    from protocol import (
        PARSE_FAIL_OBSERVATION,
        SYSTEM_PROMPT,
        format_observation,
        parse_action,
    )

VERSION = "0.1.1"


class CompactShellAgent(BaseAgent):
    SUPPORTS_ATIF = False
    SUPPORTS_WINDOWS = False

    def __init__(
        self,
        logs_dir: Path,
        model_name: str | None = None,
        max_turns: int = 20,
        command_timeout_sec: int = 60,
        observation_limit: int = 8000,
        temperature: float = 0.0,
        llm_call_kwargs: dict[str, Any] | None = None,
        extra_env: dict[str, str] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            logs_dir=logs_dir,
            model_name=model_name,
            extra_env=extra_env,
            *args,
            **kwargs,
        )
        self._max_turns = max_turns
        self._command_timeout_sec = command_timeout_sec
        self._observation_limit = observation_limit
        self._temperature = temperature
        self._llm_call_kwargs = dict(llm_call_kwargs or {})
        self._cwd = "/app"

    @staticmethod
    def name() -> str:
        return "compact-shell"

    def version(self) -> str:
        return VERSION

    async def setup(self, environment: BaseEnvironment) -> None:
        return None

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        if not self.model_name:
            raise ValueError("compact-shell requires -m / --model")
        turns: list[dict[str, Any]] = []
        n_shell = 0
        n_parse_fail = 0
        finished = False
        chat: Chat | None = None
        try:
            llm = LiteLLM(model_name=self.model_name, temperature=self._temperature)
            chat = Chat(llm)
            prompt = SYSTEM_PROMPT + "\n\n# Task\n" + instruction.strip() + "\n"
            for turn in range(1, self._max_turns + 1):
                response = await chat.chat(
                    prompt,
                    logging_path=self.logs_dir / f"turn-{turn}.txt",
                    **self._llm_call_kwargs,
                )
                text = response.content or ""
                action = parse_action(text)
                record: dict[str, Any] = {
                    "turn": turn,
                    "kind": action.kind,
                    "reason": action.reason,
                }
                if action.kind == "finish":
                    finished = True
                    turns.append(record)
                    break
                if action.kind == "invalid":
                    n_parse_fail += 1
                    record["observation"] = PARSE_FAIL_OBSERVATION
                    turns.append(record)
                    prompt = PARSE_FAIL_OBSERVATION
                    continue
                result = await environment.exec(
                    f"bash -c {shlex.quote(action.command)}",
                    cwd=self._cwd,
                    timeout_sec=self._command_timeout_sec,
                )
                n_shell += 1
                observation = format_observation(
                    result.stdout or "",
                    result.stderr or "",
                    result.return_code,
                    self._observation_limit,
                )
                record["command"] = action.command
                record["return_code"] = result.return_code
                record["observation"] = observation
                turns.append(record)
                prompt = observation
        finally:
            self._persist(context, chat, turns, n_shell, n_parse_fail, finished)

    def _persist(
        self,
        context: AgentContext,
        chat: Chat | None,
        turns: list[dict[str, Any]],
        n_shell: int,
        n_parse_fail: int,
        finished: bool,
    ) -> None:
        payload = {
            "version": VERSION,
            "finished": finished,
            "n_turns": len(turns),
            "n_shell": n_shell,
            "n_parse_fail": n_parse_fail,
            "turns": turns,
        }
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "compact-shell.json").write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        if chat is not None:
            context.n_input_tokens = chat.total_input_tokens
            context.n_output_tokens = chat.total_output_tokens
            context.n_cache_tokens = chat.total_cache_tokens
            context.cost_usd = chat.total_cost
        context.metadata = {
            "n_turns": len(turns),
            "n_shell": n_shell,
            "n_parse_fail": n_parse_fail,
            "finished": finished,
        }
