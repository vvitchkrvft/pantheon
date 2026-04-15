"""Runner loop boundaries for Pantheon."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pantheon.adapters import HermesAdapter, RunContext
from pantheon.db import (
    AgentRecord,
    GoalRecord,
    RunRecord,
    TaskRecord,
    connect_database,
    count_active_runs_for_agent,
    get_agent_for_task,
    insert_event,
    list_queued_tasks_for_goal,
    next_run_attempt_number,
    resolve_goal_for_start,
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


def _run_log_path(db_path: Path, run_id: str) -> Path:
    return db_path.parent / "logs" / f"{run_id}.log"


def _utc_now(connection) -> str:
    row = connection.execute(
        """
        SELECT strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        """
    ).fetchone()
    return str(row[0])
