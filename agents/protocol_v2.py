"""Versioned lightweight protocol: first-user rules, independent shell commands."""
from __future__ import annotations

import re
from dataclasses import dataclass

HARNESS_VERSION = "2.0.0-rc.1"
SYSTEM_PROMPT = """You are a coding agent in a Linux sandbox. The task instruction defines the contract and which files may be changed.
These harness rules and the task are supplied together as the first user message; there is no separate system-role message.

Each turn must contain exactly ONE action, without surrounding prose:
```bash
your shell command
```
or the standalone action:
```finish
```

Every command runs in a NEW bash -c process with working directory /app. Files persist, but shell state does not: cd, export, aliases and shell variables do NOT carry to the next turn. Use absolute paths, or repeat cd/export inside each command. Commands may be joined within one bash action.
Use python3, not python. Do not output tool-call JSON or multiple action fences. A finish action must be separate from every bash action; it executes no command. Finishing does not imply that your submission is correct. The hidden grader evaluates your saved task artifacts after the episode.
"""
PARSE_FAIL_OBSERVATION = "Invalid action. Send exactly one bash/sh fence OR one standalone empty finish fence. Do not combine actions. No command was executed."


@dataclass(frozen=True)
class Action:
    kind: str
    command: str = ""
    reason: str = ""


def parse_action(text: str) -> Action:
    value = (text or "").strip()
    if not value:
        return Action("invalid", reason="empty")
    if re.fullmatch(r"```finish[ \t]*(?:\r?\n[ \t]*)?```", value, re.IGNORECASE):
        return Action("finish")
    lines = value.splitlines()
    if len(lines) < 3 or not re.fullmatch(r"```(?:bash|sh)[ \t]*", lines[0], re.IGNORECASE) or lines[-1].strip() != "```":
        return Action("invalid", reason="not_one_standalone_action")
    body = "\n".join(lines[1:-1])
    # Embedded inline strings such as printf '```finish```' remain shell data.
    # Nested line-level fences are ambiguous, including heredoc Markdown: fail
    # closed instead of interpreting one of them as a finish or executing two actions.
    if any(re.match(r"^\s*```(?:bash|sh|finish)?(?:\s|`|$)", line, re.IGNORECASE) for line in lines[1:-1]):
        return Action("invalid", reason="mixed_multiple_or_nested_fences")
    if not body.strip():
        return Action("invalid", reason="empty_command")
    return Action("shell", command=body)


@dataclass(frozen=True)
class Observation:
    text: str
    stdout_chars: int
    stderr_chars: int
    original_chars: int
    truncated: bool
    retained_head_chars: int
    retained_tail_chars: int

    def metadata(self) -> dict:
        return {key: value for key, value in self.__dict__.items() if key != "text"}


def format_observation(stdout: str, stderr: str, return_code: int | None, limit: int) -> Observation:
    if type(limit) is not int or limit < 1:
        raise ValueError("observation limit must be a positive character count")
    body = f"exit {return_code if return_code is not None else 'unknown'}\n"
    body += ("stdout:\n" + stdout) if stdout else ""
    if stderr:
        body += ("\n" if stdout else "") + "stderr:\n" + stderr
    if not stdout and not stderr:
        body += "(no output)"
    original = len(body)
    head, tail = original, 0
    truncated = original > limit
    if truncated:
        marker = "\n...[truncated]...\n"
        available = max(0, limit - len(marker))
        head, tail = (available + 1) // 2, available // 2
        body = body[:head] + marker[:limit] + (body[-tail:] if tail else "")
    return Observation(body, len(stdout), len(stderr), original, truncated, head, tail)
