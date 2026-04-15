"""Runner loop boundaries for Pantheon."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pantheon.adapters import HermesAdapter, RunContext
from pantheon.db import (
    AgentRecord,
    ChildTaskCreateRecord,
    GoalRecord,
    RunRecord,
    TaskRecord,
    count_non_terminal_tasks_for_goal,
    create_child_tasks,
    connect_database,
    count_active_runs_for_agent,
    get_agent_for_task,
    insert_event,
    list_queued_tasks_for_goal,
    mark_goal_complete,
    next_run_attempt_number,
    resolve_group_agent_for_goal,
    resolve_goal_for_start,
)
from pantheon.structured_output import (
    CompletionJudgmentPayload,
    ProposedTask,
    TaskProposalPayload,
    parse_control_payload,
)


@dataclass(frozen=True)
class StartGoalResult:
    goal_id: str
    started_at: str
    runs: list[RunRecord]


def start_goal_execution(
    db_path: str | Path, goal_id: str, *, adapter: HermesAdapter | None = None
) -> StartGoalResult:
    hermes_adapter = adapter or HermesAdapter()
    connection = connect_database(db_path)
    try:
        goal, _root_task = resolve_goal_for_start(connection, goal_id)
        next_dispatch = _resolve_next_dispatchable_task(
            connection, goal, raise_when_none=True
        )
        started_at = _utc_now(connection)
        connection.execute(
            """
            UPDATE goals
            SET status = 'running', started_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (started_at, started_at, goal.id),
        )
        insert_event(
            connection,
            goal_id=goal.id,
            task_id=None,
            run_id=None,
            agent_id=None,
            event_type="goal.started",
            payload={"goal_id": goal.id, "status": "running"},
            created_at=started_at,
        )
        connection.commit()

        completed_runs: list[RunRecord] = []
        while next_dispatch is not None:
            task, agent = next_dispatch
            completed_runs.append(
                _dispatch_task(
                    connection,
                    db_path=Path(db_path),
                    goal_id=goal.id,
                    task=task,
                    agent=agent,
                    adapter=hermes_adapter,
                )
            )
            next_dispatch = _resolve_next_dispatchable_task(
                connection, goal, raise_when_none=False
            )

        _reconcile_goal_state(connection, goal.id)
        return StartGoalResult(goal_id=goal.id, started_at=started_at, runs=completed_runs)
    finally:
        connection.close()


def _dispatch_task(
    connection,
    *,
    db_path: Path,
    goal_id: str,
    task: TaskRecord,
    agent: AgentRecord,
    adapter: HermesAdapter,
) -> RunRecord:
    if task.status != "queued":
        raise ValueError(f"task is not dispatchable from state {task.status}")
    if agent.status != "idle":
        raise ValueError(f"assigned agent is not idle: {agent.id}")
    if count_active_runs_for_agent(connection, agent.id) > 0:
        raise ValueError(f"assigned agent already has an active run: {agent.id}")

    attempt_number = next_run_attempt_number(connection, task.id)
    run_id = str(uuid4())
    started_at = _utc_now(connection)
    log_path = _run_log_path(db_path, run_id)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    connection.execute(
        """
        INSERT INTO runs (
            id,
            task_id,
            agent_id,
            attempt_number,
            status,
            session_id,
            pid,
            exit_code,
            error_text,
            log_path,
            usage_json,
            started_at,
            finished_at,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            task.id,
            agent.id,
            attempt_number,
            "running",
            None,
            None,
            None,
            None,
            str(log_path),
            None,
            started_at,
            None,
            started_at,
        ),
    )
    connection.execute(
        """
        UPDATE tasks
        SET status = 'running',
            started_at = COALESCE(started_at, ?),
            updated_at = ?
        WHERE id = ?
        """,
        (started_at, started_at, task.id),
    )
    connection.execute(
        """
        UPDATE agents
        SET status = 'busy', updated_at = ?
        WHERE id = ?
        """,
        (started_at, agent.id),
    )
    insert_event(
        connection,
        goal_id=goal_id,
        task_id=task.id,
        run_id=run_id,
        agent_id=agent.id,
        event_type="run.started",
        payload={"run_id": run_id, "task_id": task.id, "agent_id": agent.id},
        created_at=started_at,
    )
    insert_event(
        connection,
        goal_id=goal_id,
        task_id=task.id,
        run_id=run_id,
        agent_id=agent.id,
        event_type="task.started",
        payload={"task_id": task.id, "status": "running"},
        created_at=started_at,
    )
    connection.commit()

    try:
        adapter_run = adapter.run_task(
            agent=agent,
            task=task,
            run_context=RunContext(run_id=run_id, log_path=str(log_path)),
        )
    except Exception as exc:
        return _apply_terminal_state(
            connection,
            goal_id=goal_id,
            task=task,
            agent=agent,
            run_id=run_id,
            attempt_number=attempt_number,
            started_at=started_at,
            log_path=str(log_path),
            terminal_status="failed",
            final_text="",
            session_id=None,
            exit_code=None,
            error_text=str(exc),
            usage_json=None,
        )

    output_chunks = [
        event.payload for event in adapter_run.stream_events if event.category in {"stdout", "stderr"}
    ]
    raw_output = "".join(output_chunks)
    if raw_output:
        log_path.write_text(raw_output, encoding="utf-8")
    else:
        log_path.write_text("", encoding="utf-8")

    output_created_at = _utc_now(connection)
    if raw_output:
        insert_event(
            connection,
            goal_id=goal_id,
            task_id=task.id,
            run_id=run_id,
            agent_id=agent.id,
            event_type="run.output",
            payload={"run_id": run_id, "text": raw_output},
            created_at=output_created_at,
        )
        connection.commit()

    return _apply_terminal_state(
        connection,
        goal_id=goal_id,
        task=task,
        agent=agent,
        run_id=run_id,
        attempt_number=attempt_number,
        started_at=started_at,
        log_path=str(log_path),
        terminal_status=adapter_run.final_result.status,
        final_text=adapter_run.final_result.final_text,
        session_id=adapter_run.final_result.session_id,
        exit_code=adapter_run.final_result.exit_code,
        error_text=adapter_run.final_result.error_text,
        usage_json=adapter_run.final_result.usage_json,
    )


def _resolve_next_dispatchable_task(
    connection, goal: GoalRecord, *, raise_when_none: bool
) -> tuple[TaskRecord, AgentRecord] | None:
    first_blocking_error: str | None = None
    queued_tasks = list_queued_tasks_for_goal(connection, goal.id)
    if not queued_tasks:
        if raise_when_none:
            raise ValueError("goal has no queued tasks to dispatch")
        return None

    for task in queued_tasks:
        if not _is_task_dispatch_ready(connection, task):
            continue
        try:
            agent = get_agent_for_task(connection, task)
        except ValueError as exc:
            if first_blocking_error is None:
                first_blocking_error = str(exc)
            continue
        if agent.status != "idle":
            if first_blocking_error is None:
                first_blocking_error = f"assigned agent is not idle: {agent.id}"
            continue
        if count_active_runs_for_agent(connection, agent.id) > 0:
            if first_blocking_error is None:
                first_blocking_error = (
                    f"assigned agent already has an active run: {agent.id}"
                )
            continue
        return task, agent

    if raise_when_none and first_blocking_error is not None:
        raise ValueError(first_blocking_error)
    if raise_when_none:
        raise ValueError("goal has no dispatchable queued tasks")
    return None


def _apply_terminal_state(
    connection,
    *,
    goal_id: str,
    task: TaskRecord,
    agent: AgentRecord,
    run_id: str,
    attempt_number: int,
    started_at: str,
    log_path: str,
    terminal_status: str,
    final_text: str,
    session_id: str | None,
    exit_code: int | None,
    error_text: str | None,
    usage_json: str | None,
) -> RunRecord:
    terminal_event = {
        "complete": ("run.completed", "task.completed"),
        "failed": ("run.failed", "task.failed"),
        "cancelled": ("run.cancelled", "task.cancelled"),
    }.get(terminal_status)
    if terminal_event is None:
        raise ValueError(f"unsupported adapter terminal status {terminal_status}")

    finished_at = _utc_now(connection)
    connection.execute(
        """
        UPDATE runs
        SET status = ?,
            session_id = ?,
            exit_code = ?,
            error_text = ?,
            usage_json = ?,
            finished_at = ?
        WHERE id = ?
        """,
        (
            terminal_status,
            session_id,
            exit_code,
            error_text,
            usage_json,
            finished_at,
            run_id,
        ),
    )
    connection.execute(
        """
        UPDATE tasks
        SET status = ?,
            result_text = ?,
            completed_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (terminal_status, final_text, finished_at, finished_at, task.id),
    )
    connection.execute(
        """
        UPDATE agents
        SET status = 'idle', updated_at = ?
        WHERE id = ? AND status = 'busy'
        """,
        (finished_at, agent.id),
    )
    insert_event(
        connection,
        goal_id=goal_id,
        task_id=task.id,
        run_id=run_id,
        agent_id=agent.id,
        event_type=terminal_event[0],
        payload={"run_id": run_id, "status": terminal_status},
        created_at=finished_at,
    )
    insert_event(
        connection,
        goal_id=goal_id,
        task_id=task.id,
        run_id=run_id,
        agent_id=agent.id,
        event_type=terminal_event[1],
        payload={"task_id": task.id, "status": terminal_status},
        created_at=finished_at,
    )
    connection.commit()
    if terminal_status == "complete":
        _apply_structured_output(
            connection,
            goal_id=goal_id,
            task=task,
            agent=agent,
            run_id=run_id,
            final_text=final_text,
        )

    return RunRecord(
        id=run_id,
        task_id=task.id,
        agent_id=agent.id,
        attempt_number=attempt_number,
        status=terminal_status,
        session_id=session_id,
        pid=None,
        exit_code=exit_code,
        error_text=error_text,
        log_path=log_path,
        usage_json=usage_json,
        started_at=started_at,
        finished_at=finished_at,
        created_at=started_at,
    )


def _is_task_dispatch_ready(connection, task: TaskRecord) -> bool:
    if task.parent_task_id is None:
        return True

    row = connection.execute(
        """
        SELECT status
        FROM tasks
        WHERE id = ? AND goal_id = ?
        """,
        (task.parent_task_id, task.goal_id),
    ).fetchone()
    if row is None:
        raise ValueError(f"parent task not found: {task.parent_task_id}")
    return row["status"] == "complete"


def _reconcile_goal_state(connection, goal_id: str) -> None:
    task_rows = connection.execute(
        """
        SELECT status
        FROM tasks
        WHERE goal_id = ?
        """,
        (goal_id,),
    ).fetchall()
    if not task_rows:
        return

    statuses = {row["status"] for row in task_rows}
    if any(status not in {"complete", "failed", "cancelled"} for status in statuses):
        return
    # Without lead completion_judgment support in this slice, fully terminal work
    # does not further terminalize the goal. Per spec, the goal remains running.


def _apply_structured_output(
    connection,
    *,
    goal_id: str,
    task: TaskRecord,
    agent: AgentRecord,
    run_id: str,
    final_text: str,
) -> None:
    if agent.role != "lead":
        return

    parsed_result = parse_control_payload(final_text)
    if parsed_result.rejection_reason is not None:
        rejected_at = _utc_now(connection)
        insert_event(
            connection,
            goal_id=goal_id,
            task_id=task.id,
            run_id=run_id,
            agent_id=agent.id,
            event_type="lead.payload_rejected",
            payload={"reason": parsed_result.rejection_reason, "task_id": task.id},
            created_at=rejected_at,
        )
        connection.commit()
        return

    if parsed_result.payload is None:
        return

    if parsed_result.payload.output_type == "task_proposal":
        _apply_task_proposal(
            connection,
            goal_id=goal_id,
            task=task,
            run_id=run_id,
            agent=agent,
            proposal=parsed_result.payload.payload,
        )
        return

    if parsed_result.payload.output_type == "completion_judgment":
        _apply_completion_judgment(
            connection,
            goal_id=goal_id,
            task=task,
            run_id=run_id,
            agent=agent,
            judgment=parsed_result.payload.payload,
        )
        return

    raise ValueError(f"unsupported structured output type: {parsed_result.payload.output_type}")


def _apply_task_proposal(
    connection,
    *,
    goal_id: str,
    task: TaskRecord,
    run_id: str,
    agent: AgentRecord,
    proposal: TaskProposalPayload | CompletionJudgmentPayload,
) -> None:
    if not isinstance(proposal, TaskProposalPayload):
        raise ValueError("task_proposal handler received wrong payload type")

    created_at = _utc_now(connection)
    try:
        child_specs = _build_child_task_specs(connection, goal_id=goal_id, task=task, proposal=proposal)
    except ValueError as exc:
        insert_event(
            connection,
            goal_id=goal_id,
            task_id=task.id,
            run_id=run_id,
            agent_id=agent.id,
            event_type="lead.payload_rejected",
            payload={"reason": str(exc), "task_id": task.id},
            created_at=created_at,
        )
        connection.commit()
        return

    created_tasks = create_child_tasks(connection, created_at=created_at, tasks=child_specs)
    for created_task in created_tasks:
        insert_event(
            connection,
            goal_id=goal_id,
            task_id=created_task.id,
            run_id=None,
            agent_id=created_task.assigned_agent_id,
            event_type="task.created",
            payload={
                "task_id": created_task.id,
                "goal_id": created_task.goal_id,
                "parent_task_id": created_task.parent_task_id,
                "assigned_agent_id": created_task.assigned_agent_id,
                "depth": created_task.depth,
                "status": created_task.status,
            },
            created_at=created_at,
        )
    connection.commit()


def _apply_completion_judgment(
    connection,
    *,
    goal_id: str,
    task: TaskRecord,
    run_id: str,
    agent: AgentRecord,
    judgment: TaskProposalPayload | CompletionJudgmentPayload,
) -> None:
    if not isinstance(judgment, CompletionJudgmentPayload):
        raise ValueError("completion_judgment handler received wrong payload type")
    if judgment.judgment != "complete":
        raise ValueError(f"unsupported completion_judgment value: {judgment.judgment}")

    judged_at = _utc_now(connection)
    if count_non_terminal_tasks_for_goal(connection, goal_id) > 0:
        insert_event(
            connection,
            goal_id=goal_id,
            task_id=task.id,
            run_id=run_id,
            agent_id=agent.id,
            event_type="goal.completion_blocked",
            payload={"goal_id": goal_id, "task_id": task.id, "judgment": judgment.judgment},
            created_at=judged_at,
        )
        connection.commit()
        return

    mark_goal_complete(connection, goal_id, completed_at=judged_at)
    insert_event(
        connection,
        goal_id=goal_id,
        task_id=task.id,
        run_id=run_id,
        agent_id=agent.id,
        event_type="goal.completed",
        payload={"goal_id": goal_id, "task_id": task.id, "judgment": judgment.judgment},
        created_at=judged_at,
    )
    connection.commit()


def _build_child_task_specs(
    connection,
    *,
    goal_id: str,
    task: TaskRecord,
    proposal: TaskProposalPayload,
) -> list[ChildTaskCreateRecord]:
    task_refs = {proposed_task.ref: proposed_task for proposed_task in proposal.tasks}
    for proposed_task in proposal.tasks:
        if proposed_task.parent_ref is not None and proposed_task.parent_ref not in task_refs:
            raise ValueError(
                f"task_proposal parent_ref must resolve within the same proposal: {proposed_task.parent_ref}"
            )

    depth_by_ref = {
        proposed_task.ref: _resolve_child_depth(task_refs, proposed_task.ref, task.depth)
        for proposed_task in proposal.tasks
    }

    ordered_specs: list[tuple[int, ChildTaskCreateRecord]] = []
    task_id_by_ref = {proposed_task.ref: str(uuid4()) for proposed_task in proposal.tasks}
    for index, proposed_task in enumerate(proposal.tasks):
        assigned_agent = resolve_group_agent_for_goal(
            connection, goal_id, proposed_task.assigned_agent
        )
        if assigned_agent is None:
            raise ValueError(
                f"task_proposal assigned_agent does not resolve in the goal group: {proposed_task.assigned_agent}"
            )

        parent_task_id = (
            task.id
            if proposed_task.parent_ref is None
            else task_id_by_ref[proposed_task.parent_ref]
        )
        ordered_specs.append(
            (
                index,
                ChildTaskCreateRecord(
                id=task_id_by_ref[proposed_task.ref],
                goal_id=goal_id,
                parent_task_id=parent_task_id,
                assigned_agent_id=assigned_agent.id,
                title=proposed_task.title,
                input_text=proposed_task.input_text,
                priority=5,
                depth=depth_by_ref[proposed_task.ref],
                ),
            )
        )
    ordered_specs.sort(key=lambda item: (item[1].depth, item[0]))
    return [spec for _, spec in ordered_specs]


def _resolve_child_depth(
    task_refs: dict[str, ProposedTask], ref: str, lead_task_depth: int
) -> int:
    proposed_task = task_refs[ref]
    if proposed_task.parent_ref is None:
        return lead_task_depth + 1
    return _resolve_child_depth(task_refs, proposed_task.parent_ref, lead_task_depth) + 1


def _run_log_path(db_path: Path, run_id: str) -> Path:
    return db_path.parent / "logs" / f"{run_id}.log"


def _utc_now(connection) -> str:
    row = connection.execute(
        """
        SELECT strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        """
    ).fetchone()
    return str(row[0])
