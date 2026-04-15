"""Hermes adapter boundaries for Pantheon."""

from __future__ import annotations

import os
import re
import selectors
import subprocess
from dataclasses import dataclass
from io import BufferedReader
from typing import Protocol, cast

from pantheon.db import AgentRecord, TaskRecord


_SESSION_ID_TRAILER_PATTERN = re.compile(r"^session_id: (?P<session_id>\S+)$")


@dataclass(frozen=True)
class RunContext:
    run_id: str
    log_path: str
    parent_task_summary: str | None = None
    dependency_outputs: list[str] | None = None
    operator_note: str | None = None


@dataclass(frozen=True)
class StreamEvent:
    category: str
    payload: str


@dataclass(frozen=True)
class FinalResult:
    status: str
    final_text: str
    session_id: str | None
    exit_code: int | None
    error_text: str | None
    usage_json: str | None


@dataclass(frozen=True)
class AdapterRun:
    stream_events: list[StreamEvent]
    final_result: FinalResult


@dataclass(frozen=True)
class ProcessResult:
    stdout: str
    stderr: str
    exit_code: int


class ProcessRunner(Protocol):
    def __call__(
        self,
        command: list[str],
        *,
        cwd: str,
        env: dict[str, str],
    ) -> ProcessResult: ...


class HermesAdapter:
    """Narrow Hermes process-invocation boundary for one task execution."""

    def __init__(self, *, process_runner: ProcessRunner | None = None) -> None:
        self._process_runner = process_runner or _run_subprocess

    def run_task(
        self, agent: AgentRecord, task: TaskRecord, run_context: RunContext
    ) -> AdapterRun:
        del run_context

        command = _build_hermes_command(agent, task)
        environment = _build_subprocess_env(agent)

        stream_events = [StreamEvent(category="lifecycle", payload="started")]
        try:
            process_result = self._process_runner(
                command,
                cwd=agent.workdir,
                env=environment,
            )
        except OSError as exc:
            stream_events.append(StreamEvent(category="lifecycle", payload="failed"))
            return AdapterRun(
                stream_events=stream_events,
                final_result=FinalResult(
                    status="failed",
                    final_text="",
                    session_id=None,
                    exit_code=None,
                    error_text=str(exc),
                    usage_json=None,
                ),
            )

        if process_result.stdout:
            stream_events.append(
                StreamEvent(category="stdout", payload=process_result.stdout)
            )
        if process_result.stderr:
            stream_events.append(
                StreamEvent(category="stderr", payload=process_result.stderr)
            )
        stream_events.append(StreamEvent(category="lifecycle", payload="exited"))

        final_text, session_id = _extract_session_id(process_result.stdout)
        if process_result.exit_code == 0:
            status = "complete"
            error_text = None
        else:
            status = "failed"
            error_text = _normalize_error_text(process_result.stderr, process_result.exit_code)

        return AdapterRun(
            stream_events=stream_events,
            final_result=FinalResult(
                status=status,
                final_text=final_text,
                session_id=session_id,
                exit_code=process_result.exit_code,
                error_text=error_text,
                usage_json=None,
            ),
        )


def _build_hermes_command(agent: AgentRecord, task: TaskRecord) -> list[str]:
    # `hermes acp` is available locally, but this install exposes it only as a
    # long-running ACP server. For the narrow one-task V1 adapter, use Hermes'
    # single-query CLI path instead.
    command = [
        "hermes",
        "chat",
        "-q",
        task.input_text,
        "-Q",
        "--source",
        "tool",
    ]
    if agent.model_override:
        command.extend(["--model", agent.model_override])
    if agent.provider_override:
        command.extend(["--provider", agent.provider_override])
    return command


def _extract_session_id(stdout_text: str) -> tuple[str, str | None]:
    stripped_stdout = stdout_text.rstrip("\n")
    if not stripped_stdout:
        return "", None

    lines = stripped_stdout.split("\n")
    trailer_match = _SESSION_ID_TRAILER_PATTERN.fullmatch(lines[-1])
    if trailer_match is None:
        return stripped_stdout, None

    final_text = "\n".join(lines[:-1]).rstrip()
    return final_text, trailer_match.group("session_id")


def _build_subprocess_env(agent: AgentRecord) -> dict[str, str]:
    environment = {"HERMES_HOME": agent.hermes_home}
    path = os.environ.get("PATH")
    if path:
        environment["PATH"] = path
    return environment


def _normalize_error_text(stderr_text: str, exit_code: int) -> str:
    normalized_stderr = stderr_text.strip()
    if normalized_stderr:
        return normalized_stderr
    return f"Hermes exited with code {exit_code}"


def _run_subprocess(
    command: list[str], *, cwd: str, env: dict[str, str]
) -> ProcessResult:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )
    if process.stdout is None or process.stderr is None:
        raise OSError("failed to capture Hermes process output")

    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, data="stdout")
    selector.register(process.stderr, selectors.EVENT_READ, data="stderr")

    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    while selector.get_map():
        for key, _mask in selector.select():
            stream = cast(BufferedReader, key.fileobj)
            chunk = stream.read1(4096)
            if not chunk:
                selector.unregister(stream)
                stream.close()
                continue
            if key.data == "stdout":
                stdout_chunks.append(chunk)
            else:
                stderr_chunks.append(chunk)

    exit_code = process.wait()
    return ProcessResult(
        stdout=b"".join(stdout_chunks).decode("utf-8", errors="replace"),
        stderr=b"".join(stderr_chunks).decode("utf-8", errors="replace"),
        exit_code=exit_code,
    )
