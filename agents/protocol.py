"""Frozen CompactShell grammar. Mechanism only; no JSON tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import re

Kind = Literal["shell", "finish", "invalid"]

BASH_FENCE = re.compile(r"```(?:bash|sh)\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)
FINISH_FENCE = re.compile(r"```finish\s*```", re.IGNORECASE)

SYSTEM_PROMPT = """\
You are a coding agent in a Linux sandbox. The task instruction is the spec.
You may inspect and edit files, and you may run commands.

Output exactly one action per turn, using one of these two fences and nothing else required:

```bash
<command>
```

```finish
```

Rules:
- One bash fence runs that command in /app. Do not wrap it in JSON.
- ```finish``` ends the episode. The hidden grader scores the sandbox after you stop.
- If you need several commands, run them across turns or join with && / ;
- Do not invent other fences or tool-call JSON.
"""

PARSE_FAIL_OBSERVATION = (
    "No action parsed. Output exactly one ```bash command ``` fence "
    "or a ```finish``` fence."
)


@dataclass(frozen=True)
class Action:
    kind: Kind
    command: str = ""
    reason: str = ""


def parse_action(text: str) -> Action:
    if not text or not text.strip():
        return Action(kind="invalid", reason="empty")
    if FINISH_FENCE.search(text):
        return Action(kind="finish")
    blocks = [block.strip() for block in BASH_FENCE.findall(text)]
    blocks = [block for block in blocks if block]
    if len(blocks) == 1:
        return Action(kind="shell", command=blocks[0])
    if len(blocks) > 1:
        return Action(kind="invalid", reason="multiple_bash_fences")
    return Action(kind="invalid", reason="no_fence")


def format_observation(stdout: str, stderr: str, return_code: int, limit: int) -> str:
    body = f"exit {return_code}\n"
    if stdout:
        body += f"stdout:\n{stdout}"
    if stderr:
        if stdout:
            body += "\n"
        body += f"stderr:\n{stderr}"
    if not stdout and not stderr:
        body += "(no output)"
    if len(body) > limit:
        body = body[: max(0, limit - 20)] + "\n...[truncated]"
    return body
