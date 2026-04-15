"""Hermes adapter boundaries for Pantheon."""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TextIO

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
    payload: dict[str, Any]


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


@dataclass(frozen=True)
class AcpPromptResult:
    session_id: str
    stop_reason: str
    final_text: str
    stream_events: list[StreamEvent]
    usage_json: str | None
    error_text: str | None = None


class ProcessRunner(Protocol):
    def __call__(
        self,
        command: list[str],
        *,
        cwd: str,
        env: dict[str, str],
    ) -> ProcessResult: ...


class AcpClient(Protocol):
    def run_prompt(
        self,
        *,
        command: list[str],
        cwd: str,
        env: dict[str, str],
        prompt_text: str,
    ) -> AcpPromptResult: ...


class AcpUnavailableError(RuntimeError):
    """ACP could not be used for this task before a prompt was dispatched."""


class HermesAdapter:
    """Narrow Hermes process-invocation boundary for one task execution."""

    def __init__(
        self,
        *,
        process_runner: ProcessRunner | None = None,
        acp_client: AcpClient | None = None,
    ) -> None:
        self._process_runner = process_runner or _run_subprocess
        self._acp_client = acp_client or HermesAcpClient()

    def run_task(
        self, agent: AgentRecord, task: TaskRecord, run_context: RunContext
    ) -> AdapterRun:
        # Transport selection rule for this slice:
        # 1. Prefer ACP first for every task via `hermes acp`.
        # 2. Fall back to the existing `hermes chat -q ... -Q --source tool` path
        #    only if ACP is unavailable before the prompt is sent:
        #    process launch, ACP initialize, or ACP session creation failure.
        # 3. Once a prompt is handed to ACP, Pantheon keeps the task on ACP and
        #    normalizes the terminal ACP result instead of re-running via CLI.
        try:
            return self._run_task_via_acp(agent, task, run_context)
        except AcpUnavailableError:
            return self._run_task_via_cli(agent, task, run_context)

    def _run_task_via_acp(
        self, agent: AgentRecord, task: TaskRecord, run_context: RunContext
    ) -> AdapterRun:
        del run_context

        command = _build_hermes_acp_command()
        environment = _build_subprocess_env(agent)
        try:
            acp_result = self._acp_client.run_prompt(
                command=command,
                cwd=agent.workdir,
                env=environment,
                prompt_text=task.input_text,
            )
        except AcpUnavailableError:
            raise
        except OSError as exc:
            raise AcpUnavailableError(str(exc)) from exc

        terminal_status = _normalize_acp_status(acp_result.stop_reason)
        return AdapterRun(
            stream_events=[
                StreamEvent(category="lifecycle", payload={"phase": "started"}),
                *acp_result.stream_events,
                StreamEvent(category="lifecycle", payload={"phase": "exited"}),
            ],
            final_result=FinalResult(
                status=terminal_status,
                final_text=acp_result.final_text,
                session_id=acp_result.session_id,
                exit_code=None,
                error_text=acp_result.error_text,
                usage_json=acp_result.usage_json,
            ),
        )

    def _run_task_via_cli(
        self, agent: AgentRecord, task: TaskRecord, run_context: RunContext
    ) -> AdapterRun:
        del run_context

        command = _build_hermes_cli_command(agent, task)
        environment = _build_subprocess_env(agent)

        stream_events = [StreamEvent(category="lifecycle", payload={"phase": "started"})]
        try:
            process_result = self._process_runner(
                command,
                cwd=agent.workdir,
                env=environment,
            )
        except OSError as exc:
            stream_events.append(
                StreamEvent(category="lifecycle", payload={"phase": "failed"})
            )
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
                StreamEvent(
                    category="stdout",
                    payload={"text": process_result.stdout},
                )
            )
        if process_result.stderr:
            stream_events.append(
                StreamEvent(
                    category="stderr",
                    payload={"text": process_result.stderr},
                )
            )
        stream_events.append(
            StreamEvent(category="lifecycle", payload={"phase": "exited"})
        )

        final_text, session_id = _extract_session_id(process_result.stdout)
        if process_result.exit_code == 0:
            status = "complete"
            error_text = None
        else:
            status = "failed"
            error_text = _normalize_error_text(
                process_result.stderr, process_result.exit_code
            )

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


class HermesAcpClient:
    """Minimal stdio ACP client for the Hermes `hermes acp` transport."""

    def run_prompt(
        self,
        *,
        command: list[str],
        cwd: str,
        env: dict[str, str],
        prompt_text: str,
    ) -> AcpPromptResult:
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise AcpUnavailableError(str(exc)) from exc

        if process.stdin is None or process.stdout is None or process.stderr is None:
            process.kill()
            raise AcpUnavailableError("failed to capture Hermes ACP stdio")

        inbox: queue.Queue[dict[str, Any]] = queue.Queue()
        stderr_tail: deque[str] = deque(maxlen=40)

        stdout_thread = threading.Thread(
            target=_read_json_lines,
            args=(process.stdout, inbox),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_read_stderr_lines,
            args=(process.stderr, stderr_tail),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        next_id = 0
        prompt_dispatched = False

        def request(
            method: str,
            params: dict[str, Any],
            *,
            text_chunks: list[str] | None = None,
            stream_events: list[StreamEvent] | None = None,
        ) -> dict[str, Any]:
            nonlocal next_id
            next_id += 1
            request_id = next_id
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
            stdin = process.stdin
            if stdin is None:
                raise AcpUnavailableError("Hermes ACP stdin is unavailable")
            try:
                stdin.write(json.dumps(payload) + "\n")
                stdin.flush()
            except OSError as exc:
                raise AcpUnavailableError(str(exc)) from exc

            while True:
                if process.poll() is not None and inbox.empty():
                    stderr_text = "\n".join(stderr_tail).strip()
                    if prompt_dispatched:
                        raise RuntimeError(
                            stderr_text or "Hermes ACP process exited before responding"
                        )
                    raise AcpUnavailableError(
                        stderr_text or "Hermes ACP process exited before responding"
                    )

                try:
                    message = inbox.get(timeout=0.1)
                except queue.Empty:
                    continue

                if _handle_acp_server_message(
                    message=message,
                    process=process,
                    cwd=cwd,
                    text_chunks=text_chunks,
                    stream_events=stream_events,
                ):
                    continue
                if message.get("id") != request_id:
                    continue
                if "error" in message:
                    error = message["error"]
                    error_text = str(error.get("message") or error)
                    if prompt_dispatched:
                        raise RuntimeError(error_text)
                    raise AcpUnavailableError(error_text)
                result = message.get("result")
                if isinstance(result, dict):
                    return result
                return {}

        try:
            request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {
                        "fs": {
                            "readTextFile": True,
                            "writeTextFile": True,
                        }
                    },
                    "clientInfo": {
                        "name": "pantheon",
                        "title": "Pantheon",
                        "version": "0.0.0",
                    },
                },
            )
            session = request(
                "session/new",
                {
                    "cwd": cwd,
                    "mcpServers": [],
                },
            )
            session_id = str(session.get("sessionId") or "").strip()
            if not session_id:
                raise AcpUnavailableError("Hermes ACP did not return a sessionId")

            final_text_chunks: list[str] = []
            stream_events: list[StreamEvent] = []
            prompt_dispatched = True
            prompt_response = request(
                "session/prompt",
                {
                    "sessionId": session_id,
                    "prompt": [
                        {
                            "type": "text",
                            "text": prompt_text,
                        }
                    ],
                },
                text_chunks=final_text_chunks,
                stream_events=stream_events,
            )
            stop_reason = str(prompt_response.get("stopReason") or "end_turn")
            usage_json = _serialize_acp_usage(prompt_response.get("usage"))
            error_text = None
            if stop_reason == "refusal":
                error_text = "Hermes ACP refused the prompt"
            return AcpPromptResult(
                session_id=session_id,
                stop_reason=stop_reason,
                final_text="".join(final_text_chunks),
                stream_events=stream_events,
                usage_json=usage_json,
                error_text=error_text,
            )
        finally:
            _close_process(process)


def _build_hermes_acp_command() -> list[str]:
    return ["hermes", "acp"]


def _build_hermes_cli_command(agent: AgentRecord, task: TaskRecord) -> list[str]:
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


def _normalize_acp_status(stop_reason: str) -> str:
    if stop_reason == "cancelled":
        return "cancelled"
    if stop_reason == "refusal":
        return "failed"
    return "complete"


def _serialize_acp_usage(usage: Any) -> str | None:
    if not isinstance(usage, dict):
        return None
    return json.dumps(usage, sort_keys=True)


def _read_json_lines(stdout: TextIO, inbox: queue.Queue[dict[str, Any]]) -> None:
    for line in stdout:
        text = line.strip()
        if not text:
            continue
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            message = {"raw": text}
        inbox.put(message)


def _read_stderr_lines(stderr: TextIO, stderr_tail: deque[str]) -> None:
    for line in stderr:
        stderr_tail.append(line.rstrip("\n"))


def _handle_acp_server_message(
    *,
    message: dict[str, Any],
    process: subprocess.Popen[str],
    cwd: str,
    text_chunks: list[str] | None,
    stream_events: list[StreamEvent] | None,
) -> bool:
    method = message.get("method")
    if not isinstance(method, str):
        return False

    if method == "session/update":
        params = message.get("params")
        if not isinstance(params, dict):
            return True
        update = params.get("update")
        if not isinstance(update, dict):
            return True
        event = _stream_event_from_acp_update(update)
        if event is None:
            return True
        if event.category == "stdout":
            text = str(event.payload.get("text") or "")
            if text_chunks is not None:
                text_chunks.append(text)
        if stream_events is not None:
            stream_events.append(event)
        return True

    if process.stdin is None:
        return True

    response: dict[str, Any]
    message_id = message.get("id")
    params = message.get("params")
    if not isinstance(params, dict):
        params = {}

    if method == "session/request_permission":
        response = {
            "jsonrpc": "2.0",
            "id": message_id,
            "result": {
                "outcome": {
                    "outcome": "allow_once",
                }
            },
        }
    elif method == "fs/read_text_file":
        try:
            path = _ensure_path_within_cwd(str(params.get("path") or ""), cwd)
            content = path.read_text(encoding="utf-8") if path.exists() else ""
            line = params.get("line")
            limit = params.get("limit")
            if isinstance(line, int) and line > 1:
                lines = content.splitlines(keepends=True)
                start = line - 1
                end = start + limit if isinstance(limit, int) and limit > 0 else None
                content = "".join(lines[start:end])
            response = {
                "jsonrpc": "2.0",
                "id": message_id,
                "result": {
                    "content": content,
                },
            }
        except Exception as exc:
            response = _jsonrpc_error(message_id, -32602, str(exc))
    elif method == "fs/write_text_file":
        try:
            path = _ensure_path_within_cwd(str(params.get("path") or ""), cwd)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(params.get("content") or ""), encoding="utf-8")
            response = {
                "jsonrpc": "2.0",
                "id": message_id,
                "result": None,
            }
        except Exception as exc:
            response = _jsonrpc_error(message_id, -32602, str(exc))
    else:
        response = _jsonrpc_error(
            message_id,
            -32601,
            f"ACP client method '{method}' is not supported by Pantheon",
        )

    stdin = process.stdin
    if stdin is None:
        return True
    stdin.write(json.dumps(response) + "\n")
    stdin.flush()
    return True


def _stream_event_from_acp_update(update: dict[str, Any]) -> StreamEvent | None:
    session_update = str(update.get("sessionUpdate") or "").strip()
    if not session_update:
        return None

    text = _extract_acp_update_text(update.get("content"))

    if session_update == "agent_message_chunk" and text:
        return StreamEvent(
            category="stdout",
            payload={"text": text},
        )

    metadata = _normalize_acp_update_metadata(update)
    payload: dict[str, Any] = {"kind": session_update}
    if text:
        payload["text"] = text
    if metadata:
        payload["metadata"] = metadata

    return StreamEvent(
        category="structured_output",
        payload=payload,
    )


def _extract_acp_update_text(content: Any) -> str:
    if not isinstance(content, dict):
        return ""
    text_value = content.get("text")
    if isinstance(text_value, str):
        return text_value
    return ""


def _normalize_acp_update_metadata(update: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    call_id = update.get("callId")
    if isinstance(call_id, str) and call_id:
        metadata["call_id"] = call_id

    content = update.get("content")
    if isinstance(content, dict):
        tool_name = content.get("toolName")
        if isinstance(tool_name, str) and tool_name:
            metadata["tool_name"] = tool_name

    return metadata


def _jsonrpc_error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _ensure_path_within_cwd(path_text: str, cwd: str) -> Path:
    candidate = Path(path_text)
    if not candidate.is_absolute():
        raise PermissionError("ACP file-system paths must be absolute")
    resolved = candidate.resolve()
    root = Path(cwd).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PermissionError(
            f"path '{resolved}' is outside the session cwd '{root}'"
        ) from exc
    return resolved


def _close_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=2)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def _run_subprocess(
    command: list[str], *, cwd: str, env: dict[str, str]
) -> ProcessResult:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = process.communicate()
    return ProcessResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=process.returncode,
    )
