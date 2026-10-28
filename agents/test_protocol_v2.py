import pytest

from agents.protocol_v2 import HARNESS_VERSION, format_observation, parse_action


@pytest.mark.parametrize(
    "value", ("```finish```", "```finish\n```", " \n```finish\n```\n ")
)
def test_standalone_finish(value):
    assert parse_action(value).kind == "finish"


@pytest.mark.parametrize(
    "value",
    (
        "```bash\necho hi\n```\n```finish```",
        "```finish```\n```bash\necho hi\n```",
        "```bash\necho one\n```\n```sh\necho two\n```",
        "done\n```finish```",
        "```finish\ndone\n```",
        "",
        '{"tool":"bash"}',
        "```bash\ncat <<'EOF'\n```finish```\nEOF\n```",
    ),
)
def test_mixed_multiple_or_ambiguous_actions_are_invalid(value):
    assert parse_action(value).kind == "invalid"


def test_finish_literal_inside_shell_string_is_not_an_action():
    text = "```bash\nprintf '%s' '```finish```'\n```"
    action = parse_action(text)
    assert action.kind == "shell" and "```finish```" in action.command
    assert parse_action("```sh\ncd /app/repo && python3 client.py\n```").kind == "shell"


def test_observation_is_deterministic_head_and_tail():
    stdout, stderr = "BEGIN:" + "x" * 1000, "FINAL ASSERTION ERROR"
    first = format_observation(stdout, stderr, 1, 100)
    assert first == format_observation(stdout, stderr, 1, 100)
    assert len(first.text) == 100 and first.text.startswith("exit 1\nstdout:\nBEGIN:")
    assert first.text.endswith(stderr) and first.truncated
    assert first.stdout_chars == len(stdout) and first.stderr_chars == len(stderr)
    assert (
        first.original_chars > 100
        and first.retained_head_chars > 0
        and first.retained_tail_chars > 0
    )


@pytest.mark.parametrize("limit", (1, 4, 16, 19, 20))
def test_small_observation_limit_is_respected(limit):
    assert len(format_observation("abc" * 100, "tail", 0, limit).text) <= limit


def test_empty_observation_and_version():
    assert format_observation("", "", 0, 100).text == "exit 0\n(no output)"
    assert HARNESS_VERSION == "2.0.0-rc.1"


@pytest.mark.parametrize("limit", (0, -1, True))
def test_invalid_observation_limit(limit):
    with pytest.raises(ValueError):
        format_observation("", "", 0, limit)
