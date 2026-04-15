"""Hermes adapter boundaries for Pantheon."""

from __future__ import annotations

import json
from dataclasses import dataclass

from pantheon.db import AgentRecord, TaskRecord


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


class HermesAdapter:
    """Narrow Hermes process-invocation boundary for one task execution."""

    def run_task(
        self, agent: AgentRecord, task: TaskRecord, run_context: RunContext
    ) -> AdapterRun:
        usage_payload = {
            "adapter": "stub-hermes",
            "agent_role": agent.role,
            "task_id": task.id,
        }
        return AdapterRun(
            stream_events=[
                StreamEvent(category="lifecycle", payload="started"),
                StreamEvent(
                    category="stdout", payload="stub Hermes execution completed\n"
                ),
                StreamEvent(category="lifecycle", payload="exited"),
            ],
            final_result=FinalResult(
                status="complete",
                final_text="stub Hermes execution completed",
                session_id=f"stub-session-{run_context.run_id}",
                exit_code=0,
                error_text=None,
                usage_json=json.dumps(usage_payload, sort_keys=True),
            ),
        )
