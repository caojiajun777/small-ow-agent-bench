from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from protocol import PARSE_FAIL_OBSERVATION, format_observation, parse_action


def test_bash_fence():
    action = parse_action("```bash\nls /app/repo\n```")
    assert action.kind == "shell"
    assert action.command == "ls /app/repo"


def test_sh_alias():
    action = parse_action("```sh\ncat instruction.md\n```")
    assert action.kind == "shell"
    assert action.command == "cat instruction.md"


def test_finish():
    assert parse_action("```finish```").kind == "finish"
    assert parse_action("done\n```finish```\n").kind == "finish"


def test_finish_wins_over_bash():
    text = "```bash\necho hi\n```\n```finish```"
    assert parse_action(text).kind == "finish"


def test_json_tool_is_invalid():
    text = '{"tool":"shell","arguments":{"command":"ls"}}'
    action = parse_action(text)
    assert action.kind == "invalid"


def test_multiple_fences_invalid():
    text = "```bash\nls\n```\n```bash\npwd\n```"
    assert parse_action(text).kind == "invalid"
    assert parse_action(text).reason == "multiple_bash_fences"


def test_empty_invalid():
    assert parse_action("").kind == "invalid"
    assert parse_action("I will look around").kind == "invalid"


def test_observation_truncates():
    out = format_observation("x" * 50, "", 0, limit=40)
    assert out.endswith("...[truncated]")
    assert PARSE_FAIL_OBSERVATION.startswith("No action parsed")
