from dataclasses import dataclass

from pantheon.adapters import HermesAdapter, ProcessResult, RunContext
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


def test_hermes_adapter_normalizes_successful_quiet_mode_output() -> None:
    process_runner = RecordingProcessRunner(
        stdout="done\n\nsession_id: sess-123\n",
        stderr="",
        exit_code=0,
    )
    adapter = HermesAdapter(process_runner=process_runner)

    result = adapter.run_task(_agent(), _task(), _run_context())

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
    assert process_runner.calls[0].cwd == "/tmp/workdir"
    assert process_runner.calls[0].env["HERMES_HOME"] == "/tmp/hermes-home"
    assert result.stream_events == [
        type(result.stream_events[0])(category="lifecycle", payload="started"),
        type(result.stream_events[0])(
            category="stdout", payload="done\n\nsession_id: sess-123\n"
        ),
        type(result.stream_events[0])(category="lifecycle", payload="exited"),
    ]
    assert result.final_result.status == "complete"
    assert result.final_result.final_text == "done"
    assert result.final_result.session_id == "sess-123"
    assert result.final_result.exit_code == 0
    assert result.final_result.error_text is None
    assert result.final_result.usage_json is None


def test_hermes_adapter_env_is_minimized(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "/test/bin")
    monkeypatch.setenv("UNRELATED_SECRET", "do-not-forward")
    process_runner = RecordingProcessRunner(stdout="done\n\nsession_id: sess-123\n")
    adapter = HermesAdapter(process_runner=process_runner)

    adapter.run_task(_agent(), _task(), _run_context())

    assert process_runner.calls[0].env == {
        "HERMES_HOME": "/tmp/hermes-home",
        "PATH": "/test/bin",
    }


def test_hermes_adapter_normalizes_failed_process_output() -> None:
    process_runner = RecordingProcessRunner(
        stdout="partial output\n",
        stderr="provider missing\n",
        exit_code=7,
    )
    adapter = HermesAdapter(process_runner=process_runner)

    result = adapter.run_task(_agent(), _task(), _run_context())

    assert result.stream_events == [
        type(result.stream_events[0])(category="lifecycle", payload="started"),
        type(result.stream_events[0])(category="stdout", payload="partial output\n"),
        type(result.stream_events[0])(category="stderr", payload="provider missing\n"),
        type(result.stream_events[0])(category="lifecycle", payload="exited"),
    ]
    assert result.final_result.status == "failed"
    assert result.final_result.final_text == "partial output"
    assert result.final_result.session_id is None
    assert result.final_result.exit_code == 7
    assert result.final_result.error_text == "provider missing"
    assert result.final_result.usage_json is None


def test_hermes_adapter_preserves_session_id_prefixed_body_lines() -> None:
    process_runner = RecordingProcessRunner(
        stdout="intro\nsession_id: keep this line\nclosing\n",
        exit_code=0,
    )
    adapter = HermesAdapter(process_runner=process_runner)

    result = adapter.run_task(_agent(), _task(), _run_context())

    assert result.final_result.final_text == "intro\nsession_id: keep this line\nclosing"
    assert result.final_result.session_id is None


def test_hermes_adapter_extracts_only_final_trailer_session_metadata() -> None:
    process_runner = RecordingProcessRunner(
        stdout="intro\nsession_id: keep this line\nclosing\nsession_id: sess-123\n",
        exit_code=0,
    )
    adapter = HermesAdapter(process_runner=process_runner)

    result = adapter.run_task(_agent(), _task(), _run_context())

    assert (
        result.final_result.final_text
        == "intro\nsession_id: keep this line\nclosing"
    )
    assert result.final_result.session_id == "sess-123"


def test_hermes_adapter_reports_launch_failure_without_session_data() -> None:
    process_runner = RecordingProcessRunner(error=OSError("No such file or directory"))
    adapter = HermesAdapter(process_runner=process_runner)

    result = adapter.run_task(_agent(), _task(), _run_context())

    assert result.stream_events == [
        type(result.stream_events[0])(category="lifecycle", payload="started"),
        type(result.stream_events[0])(category="lifecycle", payload="failed"),
    ]
    assert result.final_result.status == "failed"
    assert result.final_result.final_text == ""
    assert result.final_result.session_id is None
    assert result.final_result.exit_code is None
    assert result.final_result.error_text == "No such file or directory"
    assert result.final_result.usage_json is None


def test_hermes_adapter_applies_model_and_provider_overrides_to_command() -> None:
    process_runner = RecordingProcessRunner(stdout="done\nsession_id: sess-123\n")
    adapter = HermesAdapter(process_runner=process_runner)

    adapter.run_task(
        _agent(
            model_override="openai/gpt-5.4-mini",
            provider_override="openai-codex",
        ),
        _task(),
        _run_context(),
    )

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


def test_hermes_adapter_extracts_final_session_id_without_blank_separator() -> None:
    process_runner = RecordingProcessRunner(
        stdout="done\nsession_id: sess-123\n",
        exit_code=0,
    )
    adapter = HermesAdapter(process_runner=process_runner)

    result = adapter.run_task(_agent(), _task(), _run_context())

    assert result.final_result.final_text == "done"
    assert result.final_result.session_id == "sess-123"
