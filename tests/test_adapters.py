from dataclasses import dataclass

from pantheon.adapters import (
    AcpPromptResult,
    AcpUnavailableError,
    HermesAdapter,
    ProcessResult,
    RunContext,
    StreamEvent,
)
from pantheon.db import AgentRecord, TaskRecord


@dataclass(frozen=True)
class ProcessCall:
    command: list[str]
    cwd: str
    env: dict[str, str]


class RecordingProcessRunner:
    def __init__(
        self,
        *,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
        error: OSError | None = None,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.error = error
        self.calls: list[ProcessCall] = []

    def __call__(
        self,
        command: list[str],
        *,
        cwd: str,
        env: dict[str, str],
    ) -> ProcessResult:
        self.calls.append(ProcessCall(command=command, cwd=cwd, env=env))
        if self.error is not None:
            raise self.error
        return ProcessResult(
            stdout=self.stdout,
            stderr=self.stderr,
            exit_code=self.exit_code,
        )


class RecordingAcpClient:
    def __init__(
        self,
        *,
        result: AcpPromptResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, object]] = []

    def run_prompt(
        self,
        *,
        command: list[str],
        cwd: str,
        env: dict[str, str],
        prompt_text: str,
    ) -> AcpPromptResult:
        self.calls.append(
            {
                "command": command,
                "cwd": cwd,
                "env": env,
                "prompt_text": prompt_text,
            }
        )
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def _agent(**overrides: str | None) -> AgentRecord:
    return AgentRecord(
        id=overrides.get("id", "agent-1") or "agent-1",
        group_id=overrides.get("group_id", "group-1") or "group-1",
        name=overrides.get("name", "lead-1") or "lead-1",
        role=overrides.get("role", "lead") or "lead",
        profile_name=overrides.get("profile_name"),
        hermes_home=overrides.get("hermes_home", "/tmp/hermes-home")
        or "/tmp/hermes-home",
        workdir=overrides.get("workdir", "/tmp/workdir") or "/tmp/workdir",
        model_override=overrides.get("model_override"),
        provider_override=overrides.get("provider_override"),
        status=overrides.get("status", "idle") or "idle",
        created_at=overrides.get("created_at", "2026-04-15T00:00:00Z")
        or "2026-04-15T00:00:00Z",
        updated_at=overrides.get("updated_at", "2026-04-15T00:00:00Z")
        or "2026-04-15T00:00:00Z",
    )


def _task() -> TaskRecord:
    return TaskRecord(
        id="task-1",
        goal_id="goal-1",
        parent_task_id=None,
        assigned_agent_id="agent-1",
        title="Task title",
        input_text="Reply with exactly: done",
        result_text=None,
        status="queued",
        priority=5,
        depth=0,
        created_at="2026-04-15T00:00:00Z",
        started_at=None,
        completed_at=None,
        updated_at="2026-04-15T00:00:00Z",
    )


def _run_context() -> RunContext:
    return RunContext(run_id="run-1", log_path="/tmp/run-1.log")


def test_hermes_adapter_prefers_acp_and_normalizes_success() -> None:
    acp_client = RecordingAcpClient(
        result=AcpPromptResult(
            session_id="acp-session-1",
            stop_reason="end_turn",
            final_text="done",
            stream_events=[
                StreamEvent(category="stdout", payload="do"),
                StreamEvent(category="stdout", payload="ne"),
            ],
            usage_json='{"input_tokens":1,"output_tokens":1,"total_tokens":2}',
        )
    )
    process_runner = RecordingProcessRunner(stdout="should not run")
    adapter = HermesAdapter(process_runner=process_runner, acp_client=acp_client)

    result = adapter.run_task(_agent(), _task(), _run_context())

    assert len(acp_client.calls) == 1
    assert acp_client.calls[0]["command"] == ["hermes", "acp"]
    assert acp_client.calls[0]["cwd"] == "/tmp/workdir"
    env = acp_client.calls[0]["env"]
    assert isinstance(env, dict)
    assert env["HERMES_HOME"] == "/tmp/hermes-home"
    assert acp_client.calls[0]["prompt_text"] == "Reply with exactly: done"
    assert process_runner.calls == []
    assert [(event.category, event.payload) for event in result.stream_events] == [
        ("lifecycle", "started"),
        ("stdout", "do"),
        ("stdout", "ne"),
        ("lifecycle", "exited"),
    ]
    assert result.final_result.status == "complete"
    assert result.final_result.final_text == "done"
    assert result.final_result.session_id == "acp-session-1"
    assert result.final_result.exit_code is None
    assert result.final_result.error_text is None
    assert result.final_result.usage_json == '{"input_tokens":1,"output_tokens":1,"total_tokens":2}'


def test_hermes_adapter_normalizes_acp_prompt_failure_without_cli_rerun() -> None:
    acp_client = RecordingAcpClient(
        result=AcpPromptResult(
            session_id="acp-session-2",
            stop_reason="refusal",
            final_text="",
            stream_events=[],
            usage_json=None,
            error_text="Hermes ACP refused the prompt",
        )
    )
    process_runner = RecordingProcessRunner(stdout="should not run")
    adapter = HermesAdapter(process_runner=process_runner, acp_client=acp_client)

    result = adapter.run_task(_agent(), _task(), _run_context())

    assert len(acp_client.calls) == 1
    assert process_runner.calls == []
    assert [(event.category, event.payload) for event in result.stream_events] == [
        ("lifecycle", "started"),
        ("lifecycle", "exited"),
    ]
    assert result.final_result.status == "failed"
    assert result.final_result.final_text == ""
    assert result.final_result.session_id == "acp-session-2"
    assert result.final_result.exit_code is None
    assert result.final_result.error_text == "Hermes ACP refused the prompt"
    assert result.final_result.usage_json is None


def test_hermes_adapter_falls_back_to_cli_when_acp_is_unavailable() -> None:
    acp_client = RecordingAcpClient(error=AcpUnavailableError("acp unavailable"))
    process_runner = RecordingProcessRunner(
        stdout="done\n\nsession_id: cli-session-1\n",
        stderr="",
        exit_code=0,
    )
    adapter = HermesAdapter(process_runner=process_runner, acp_client=acp_client)

    result = adapter.run_task(_agent(), _task(), _run_context())

    assert len(acp_client.calls) == 1
    assert len(process_runner.calls) == 1
    assert process_runner.calls[0].command == [
        "hermes",
        "chat",
        "-q",
        "Reply with exactly: done",
        "-Q",
        "--source",
        "tool",
    ]
    assert result.final_result.status == "complete"
    assert result.final_result.final_text == "done"
    assert result.final_result.session_id == "cli-session-1"
    assert result.final_result.exit_code == 0
    assert result.final_result.error_text is None
    assert result.final_result.usage_json is None


def test_hermes_adapter_selection_uses_cli_after_acp_session_rejection_only() -> None:
    acp_client = RecordingAcpClient(error=AcpUnavailableError("initialize failed"))
    process_runner = RecordingProcessRunner(
        stdout="partial output\n",
        stderr="provider missing\n",
        exit_code=7,
    )
    adapter = HermesAdapter(process_runner=process_runner, acp_client=acp_client)

    result = adapter.run_task(
        _agent(
            model_override="openai/gpt-5.4-mini",
            provider_override="openai-codex",
        ),
        _task(),
        _run_context(),
    )

    assert len(acp_client.calls) == 1
    assert len(process_runner.calls) == 1
    assert process_runner.calls[0].command == [
        "hermes",
        "chat",
        "-q",
        "Reply with exactly: done",
        "-Q",
        "--source",
        "tool",
        "--model",
        "openai/gpt-5.4-mini",
        "--provider",
        "openai-codex",
    ]
    assert result.final_result.status == "failed"
    assert result.final_result.final_text == "partial output"
    assert result.final_result.session_id is None
    assert result.final_result.exit_code == 7
    assert result.final_result.error_text == "provider missing"
    assert result.final_result.usage_json is None


def test_hermes_adapter_env_is_minimized(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "/test/bin")
    monkeypatch.setenv("UNRELATED_SECRET", "do-not-forward")
    acp_client = RecordingAcpClient(
        result=AcpPromptResult(
            session_id="acp-session-3",
            stop_reason="end_turn",
            final_text="done",
            stream_events=[],
            usage_json=None,
        )
    )
    adapter = HermesAdapter(acp_client=acp_client)

    adapter.run_task(_agent(), _task(), _run_context())

    assert acp_client.calls[0]["env"] == {
        "HERMES_HOME": "/tmp/hermes-home",
        "PATH": "/test/bin",
    }
