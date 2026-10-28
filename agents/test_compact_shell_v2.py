import asyncio
import json
from types import SimpleNamespace

import pytest

from agents import compact_shell_v2 as module
from agents.protocol_v2 import HARNESS_VERSION
from agents.test_artifacts_v2 import payload
from harbor.llms.base import ContextLengthExceededError, OutputLengthExceededError
from harbor.models.agent.context import AgentContext


class FakeChat:
    responses = []
    total_input_tokens = 10
    total_output_tokens = 5
    total_cache_tokens = 0
    total_cost = 0.01

    def __init__(self, llm):
        self.index = 0
        self.prompts = []

    async def chat(self, prompt, **kwargs):
        self.prompts.append(prompt)
        value = self.responses[self.index]
        self.index += 1
        if isinstance(value, BaseException):
            raise value
        return SimpleNamespace(content=value)


class FakeEnvironment:
    def __init__(
        self, directory, shell_error=None, capture_error=None, capture_payload=None
    ):
        self.directory = directory
        self.shell_error = shell_error
        self.capture_error = capture_error
        self.capture_payload = capture_payload
        self.events = []

    async def exec(self, command, **kwargs):
        self.events.append((command, kwargs))
        trace = json.loads((self.directory / "compact-shell-v2.json").read_text())
        if command.startswith("python3 -I -B -c "):
            assert trace["termination_reason"] != "running"
            if self.capture_error is not None:
                raise self.capture_error
            return SimpleNamespace(
                return_code=0,
                stdout=json.dumps(self.capture_payload or payload()),
                stderr="",
            )
        assert trace["turns"][-1]["status"] == "running"
        assert trace["calls"][-1]["status"] == "running"
        if self.shell_error is not None:
            raise self.shell_error
        return SimpleNamespace(
            return_code=0, stdout="BEGIN" + "x" * 1000, stderr="THE FINAL ERROR"
        )


def prepare(tmp_path, monkeypatch, responses, **kwargs):
    monkeypatch.setattr(module, "LiteLLM", lambda **kwargs: None)
    monkeypatch.setattr(module, "Chat", FakeChat)
    monkeypatch.setattr(FakeChat, "responses", responses)
    agent = module.CompactShellV2Agent(
        logs_dir=tmp_path,
        task_id="review-mean-wrong",
        model_name="mock",
        max_turns=len(responses),
        observation_limit=100,
        **kwargs,
    )
    context = AgentContext()
    return agent, context


def read_trace(directory):
    return json.loads((directory / "compact-shell-v2.json").read_text())


def test_normal_run_has_one_final_capture_full_logs_and_checkpoint(
    tmp_path, monkeypatch
):
    agent, context = prepare(
        tmp_path,
        monkeypatch,
        ["```bash\ncd /app/repo && python3 client.py\n```", "```finish\n```"],
    )
    environment = FakeEnvironment(tmp_path)
    asyncio.run(agent.run("the task", environment, context))
    trace = read_trace(tmp_path)
    assert (
        agent.version()
        == trace["version"]
        == trace["harness_version"]
        == HARNESS_VERSION
    )
    assert trace["termination_reason"] == "finish" and trace["finished"]
    assert trace["n_shell"] == 1 and trace["n_turns"] == 2
    assert len(environment.events) == 2 and environment.events[0][1]["cwd"] == "/app"
    assert (
        "NEW bash" in agent._chat.prompts[0]
        and "first user message" in agent._chat.prompts[0]
    )
    assert trace["runtime_contract"]["initial_message_role"] == "user"
    assert trace["turns"][0]["observation_metadata"]["truncated"]
    assert (
        tmp_path / trace["turns"][0]["stdout_path"]
    ).read_text() == "BEGIN" + "x" * 1000
    assert (
        tmp_path / trace["turns"][0]["stderr_path"]
    ).read_text() == "THE FINAL ERROR"
    assert agent._chat.prompts[1].endswith("THE FINAL ERROR")
    assert context.metadata["artifact_capture_status"] == "complete"
    manifest = json.loads((tmp_path / "artifacts/manifest.json").read_text())
    assert (
        manifest["status"] == "complete"
        and manifest["atomic"] is False
        and manifest["final_state_verified"] is False
    )


def test_invalid_mixed_action_does_not_execute_shell_and_reaches_turn_cap(
    tmp_path, monkeypatch
):
    agent, context = prepare(
        tmp_path, monkeypatch, ["```bash\necho no\n```\n```finish```"]
    )
    environment = FakeEnvironment(tmp_path)
    asyncio.run(agent.run("task", environment, context))
    trace = read_trace(tmp_path)
    assert trace["termination_reason"] == "max_turns" and not trace["finished"]
    assert trace["n_parse_fail"] == 1 and trace["n_shell_attempts"] == 0
    assert len(environment.events) == 1


@pytest.mark.parametrize(
    "error,reason",
    (
        (RuntimeError("provider failed"), "api_error"),
        (asyncio.CancelledError(), "cancelled"),
    ),
)
def test_api_error_or_cancel_preserves_trace_and_attempts_final_capture(
    tmp_path, monkeypatch, error, reason
):
    agent, context = prepare(tmp_path, monkeypatch, [error])
    environment = FakeEnvironment(tmp_path)
    with pytest.raises(type(error)):
        asyncio.run(agent.run("task", environment, context))
    trace = read_trace(tmp_path)
    assert trace["termination_reason"] == reason and trace["n_turns"] == 0
    assert trace["calls"][0]["error_type"] == type(error).__name__
    assert trace["calls"][0]["elapsed_seconds"] >= 0
    assert (
        trace["artifact_capture_status"] == "complete" and len(environment.events) == 1
    )


@pytest.mark.parametrize(
    "error,reason",
    (
        (OutputLengthExceededError("token limit"), "output_limit"),
        (ContextLengthExceededError("context limit"), "context_limit"),
    ),
)
def test_llm_budget_exhaustion_is_final_and_archives_existing_artifacts(
    tmp_path, monkeypatch, error, reason
):
    agent, context = prepare(
        tmp_path, monkeypatch, ["```bash\nprintf '{}' > /app/review.json\n```", error]
    )
    environment = FakeEnvironment(tmp_path)
    asyncio.run(agent.run("task", environment, context))
    trace = read_trace(tmp_path)
    assert trace["termination_reason"] == reason and not trace["finished"]
    assert trace["exception_type"] == type(error).__name__
    # n_turns continues to count complete responses, not failed API attempts.
    assert trace["n_turns"] == trace["n_shell"] == trace["n_shell_attempts"] == 1
    assert trace["n_parse_fail"] == 0 and len(agent._chat.prompts) == 2
    call = trace["calls"][-1]
    assert call["kind"] == "api" and call["turn"] == 2
    assert call["status"] == "budget_exceeded" and call["termination_reason"] == reason
    assert call["elapsed_seconds"] >= 0
    assert len(environment.events) == 2  # One successful action; one final capture.
    assert context.metadata["termination_reason"] == reason
    assert context.metadata["artifact_capture_status"] == "complete"
    assert (tmp_path / "artifacts/review.json").read_bytes() == b"{}\n"
    manifest = json.loads((tmp_path / "artifacts/manifest.json").read_text())
    assert manifest["termination_reason"] == reason


@pytest.mark.parametrize(
    "partial",
    (
        "```bash\ncat > /app/review.json <<'EOF'\n{",
        "```bash\nrm /app/review.json\n```",
        "```finish```",
    ),
)
def test_truncated_response_is_archived_but_never_parsed_or_executed(
    tmp_path, monkeypatch, partial
):
    import hashlib

    error = OutputLengthExceededError("token limit", truncated_response=partial)
    agent, context = prepare(tmp_path, monkeypatch, [error])
    environment = FakeEnvironment(tmp_path)
    asyncio.run(agent.run("task", environment, context))
    trace = read_trace(tmp_path)
    assert trace["termination_reason"] == "output_limit" and not trace["finished"]
    assert trace["n_turns"] == trace["n_shell_attempts"] == trace["n_parse_fail"] == 0
    assert len(environment.events) == 1  # Capture only, not a model shell action.
    call = trace["calls"][0]
    archived = (tmp_path / call["truncated_response_path"]).read_bytes()
    assert archived == partial.encode("utf-8")
    assert hashlib.sha256(archived).hexdigest() == call["truncated_response_sha256"]
    assert call["truncated_response_chars"] == len(partial)


def test_exception_message_does_not_turn_upstream_failure_into_budget_outcome(
    tmp_path, monkeypatch
):
    error = RuntimeError("OutputLengthExceededError or context window exceeded")
    agent, context = prepare(tmp_path, monkeypatch, [error])
    with pytest.raises(RuntimeError, match="context window exceeded"):
        asyncio.run(agent.run("task", FakeEnvironment(tmp_path), context))
    assert read_trace(tmp_path)["termination_reason"] == "api_error"


def test_budget_exception_outside_model_call_is_not_swallowed(tmp_path, monkeypatch):
    error = ContextLengthExceededError("unexpected shell backend failure")
    agent, context = prepare(tmp_path, monkeypatch, ["```bash\necho hi\n```"])
    environment = FakeEnvironment(tmp_path, shell_error=error)
    with pytest.raises(ContextLengthExceededError):
        asyncio.run(agent.run("task", environment, context))
    assert read_trace(tmp_path)["termination_reason"] == "command_error"


def test_command_timeout_is_not_a_parse_failure(tmp_path, monkeypatch):
    agent, context = prepare(tmp_path, monkeypatch, ["```bash\nsleep 99\n```"])
    environment = FakeEnvironment(tmp_path, shell_error=TimeoutError())
    with pytest.raises(TimeoutError):
        asyncio.run(agent.run("task", environment, context))
    trace = read_trace(tmp_path)
    assert (
        trace["termination_reason"] == "command_timeout" and trace["n_parse_fail"] == 0
    )
    assert trace["n_shell_attempts"] == 1 and trace["n_shell"] == 0
    assert trace["turns"][0]["status"] == "command_timeout"


def test_actual_task_cancellation_is_checkpointed_before_exec(tmp_path, monkeypatch):
    agent, context = prepare(tmp_path, monkeypatch, ["```bash\nsleep 99\n```"])
    environment = FakeEnvironment(tmp_path)

    async def work():
        started = asyncio.Event()
        original = environment.exec

        async def blocked(command, **kwargs):
            if command.startswith("bash -c "):
                trace = read_trace(tmp_path)
                assert trace["turns"][-1]["status"] == "running"
                started.set()
                await asyncio.Event().wait()
            return await original(command, **kwargs)

        environment.exec = blocked
        task = asyncio.create_task(agent.run("task", environment, context))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(work())
    assert read_trace(tmp_path)["termination_reason"] == "cancelled"
    assert context.metadata["artifact_capture_status"] == "complete"


def test_capture_failure_does_not_replace_successful_finish(tmp_path, monkeypatch):
    agent, context = prepare(tmp_path, monkeypatch, ["```finish```"])
    environment = FakeEnvironment(
        tmp_path, capture_error=RuntimeError("do not expose me")
    )
    asyncio.run(agent.run("task", environment, context))
    trace = read_trace(tmp_path)
    assert trace["termination_reason"] == "finish" and trace["finished"]
    assert trace["artifact_capture_status"] == "error"
    assert "do not expose me" not in (tmp_path / "artifacts/manifest.json").read_text()


def test_missing_submission_stays_incomplete_not_infrastructure_error(
    tmp_path, monkeypatch
):
    agent, context = prepare(tmp_path, monkeypatch, ["```finish```"])
    environment = FakeEnvironment(tmp_path, capture_payload=payload(missing=True))
    asyncio.run(agent.run("task", environment, context))
    assert read_trace(tmp_path)["artifact_capture_status"] == "incomplete"


def test_archive_disk_error_does_not_mask_model_api_error(tmp_path, monkeypatch):
    agent, context = prepare(
        tmp_path, monkeypatch, [RuntimeError("original model failure")]
    )
    real_write = module.write_json_atomic

    def write(path, value):
        if path.name == "manifest.json":
            raise OSError("archive unavailable")
        return real_write(path, value)

    def save(*args):
        raise OSError("archive unavailable")

    monkeypatch.setattr(module, "save_capture", save)
    monkeypatch.setattr(module, "write_json_atomic", write)
    with pytest.raises(RuntimeError, match="original model failure"):
        asyncio.run(agent.run("task", FakeEnvironment(tmp_path), context))
    trace = read_trace(tmp_path)
    assert (
        trace["termination_reason"] == "api_error"
        and trace["artifact_capture_status"] == "error"
    )
    assert trace["finalization_errors"][0]["stage"] == "artifact_finalization"


@pytest.mark.parametrize(
    "extra", ({"task_id": "review-mutates-rank"}, {"version_label": "0.1.1"})
)
def test_unknown_task_and_misleading_version_rejected(tmp_path, extra):
    kwargs = {"task_id": "review-mean-wrong", **extra}
    with pytest.raises(ValueError):
        module.CompactShellV2Agent(logs_dir=tmp_path, model_name="mock", **kwargs)


def test_real_chat_history_uses_first_user_role_without_system_injection(
    tmp_path, monkeypatch
):
    from harbor.llms.chat import Chat as RealChat

    class Model:
        async def call(self, prompt, message_history, **kwargs):
            assert message_history == []
            assert "shell state does not" in prompt
            return SimpleNamespace(
                content="```finish```",
                response_id=None,
                usage=None,
                reasoning_content=None,
                prompt_token_ids=None,
                completion_token_ids=None,
                logprobs=None,
                extra=None,
            )

    monkeypatch.setattr(module, "LiteLLM", lambda **kwargs: Model())
    monkeypatch.setattr(module, "Chat", RealChat)
    agent = module.CompactShellV2Agent(
        logs_dir=tmp_path, task_id="review-mean-wrong", model_name="mock"
    )
    asyncio.run(agent.run("task", FakeEnvironment(tmp_path), AgentContext()))
    assert [message["role"] for message in agent._chat.messages] == [
        "user",
        "assistant",
    ]


def test_actual_command_deadline_is_bounded_and_final_capture_still_runs(
    tmp_path, monkeypatch
):
    agent, context = prepare(
        tmp_path, monkeypatch, ["```bash\nsleep 99\n```"], command_timeout_sec=0.01
    )
    environment = FakeEnvironment(tmp_path)
    original = environment.exec

    async def exec_command(command, **kwargs):
        if command.startswith("bash -c "):
            await asyncio.sleep(1)
        return await original(command, **kwargs)

    environment.exec = exec_command
    with pytest.raises(TimeoutError):
        asyncio.run(agent.run("task", environment, context))
    trace = read_trace(tmp_path)
    assert trace["termination_reason"] == "command_timeout"
    assert trace["artifact_capture_status"] == "complete"
