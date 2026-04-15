"""SQLite bootstrap and persistence helpers for Pantheon."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

PathLike = str | Path

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS groups (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        group_id TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        profile_name TEXT,
        hermes_home TEXT NOT NULL,
        workdir TEXT NOT NULL,
        model_override TEXT,
        provider_override TEXT,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
        UNIQUE (group_id, name),
        CHECK (role IN ('lead', 'worker')),
        CHECK (status IN ('idle', 'busy', 'disabled', 'error'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS goals (
        id TEXT PRIMARY KEY,
        group_id TEXT NOT NULL,
        title TEXT NOT NULL,
        status TEXT NOT NULL,
        root_task_id TEXT,
        started_at TEXT,
        completed_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
        FOREIGN KEY (root_task_id) REFERENCES tasks(id) ON DELETE SET NULL,
        CHECK (status IN ('draft', 'queued', 'running', 'complete', 'failed', 'cancelled'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        goal_id TEXT NOT NULL,
        parent_task_id TEXT,
        assigned_agent_id TEXT NOT NULL,
        title TEXT NOT NULL,
        input_text TEXT NOT NULL,
        result_text TEXT,
        status TEXT NOT NULL,
        priority INTEGER NOT NULL DEFAULT 5,
        depth INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE,
        FOREIGN KEY (parent_task_id) REFERENCES tasks(id) ON DELETE RESTRICT,
        FOREIGN KEY (assigned_agent_id) REFERENCES agents(id) ON DELETE RESTRICT,
        CHECK (status IN ('queued', 'running', 'complete', 'failed', 'cancelled')),
        CHECK (priority >= 0),
        CHECK (depth >= 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        attempt_number INTEGER NOT NULL,
        status TEXT NOT NULL,
        session_id TEXT,
        pid INTEGER,
        exit_code INTEGER,
        error_text TEXT,
        log_path TEXT NOT NULL,
        usage_json TEXT,
        started_at TEXT,
        finished_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
        FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE RESTRICT,
        UNIQUE (task_id, attempt_number),
        CHECK (attempt_number >= 1),
        CHECK (status IN ('queued', 'running', 'complete', 'failed', 'cancelled'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        goal_id TEXT,
        task_id TEXT,
        run_id TEXT,
        agent_id TEXT,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE,
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
        FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE,
        FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_agents_group_id
    ON agents(group_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_goals_group_id
    ON goals(group_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tasks_goal_id
    ON tasks(goal_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tasks_parent_task_id
    ON tasks(parent_task_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tasks_assigned_agent_status
    ON tasks(assigned_agent_id, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tasks_goal_status
    ON tasks(goal_id, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tasks_dispatch_order
    ON tasks(status, depth, priority, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_runs_task_id
    ON runs(task_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_runs_agent_id_status
    ON runs(agent_id, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_events_goal_created_at
    ON events(goal_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_events_task_created_at
    ON events(task_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_events_run_created_at
    ON events(run_id, created_at)
    """,
)


@dataclass(frozen=True)
class GroupRecord:
    id: str
    name: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class AgentRecord:
    id: str
    group_id: str
    name: str
    role: str
    profile_name: str | None
    hermes_home: str
    workdir: str
    model_override: str | None
    provider_override: str | None
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class GoalRecord:
    id: str
    group_id: str
    title: str
    status: str
    root_task_id: str | None
    started_at: str | None
    completed_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class TaskRecord:
    id: str
    goal_id: str
    parent_task_id: str | None
    assigned_agent_id: str
    title: str
    input_text: str
    result_text: str | None
    status: str
    priority: int
    depth: int
    created_at: str
    started_at: str | None
    completed_at: str | None
    updated_at: str


@dataclass(frozen=True)
class RunRecord:
    id: str
    task_id: str
    agent_id: str
    attempt_number: int
    status: str
    session_id: str | None
    pid: int | None
    exit_code: int | None
    error_text: str | None
    log_path: str
    usage_json: str | None
    started_at: str | None
    finished_at: str | None
    created_at: str


@dataclass(frozen=True)
class EventRecord:
    id: str
    goal_id: str | None
    task_id: str | None
    run_id: str | None
    agent_id: str | None
    event_type: str
    payload_json: str
    created_at: str


@dataclass(frozen=True)
class GoalSubmissionRecord:
    goal: GoalRecord
    root_task: TaskRecord


@dataclass(frozen=True)
class GoalStatusTaskRecord:
    id: str
    assigned_agent_id: str
    title: str
    status: str
    depth: int


@dataclass(frozen=True)
class GoalStatusRunRecord:
    id: str
    task_id: str
    agent_id: str
    attempt_number: int
    status: str
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True)
class GoalStatusRecord:
    id: str
    title: str
    status: str
    root_task_id: str | None
    tasks: list[GoalStatusTaskRecord]
    runs: list[GoalStatusRunRecord]


@dataclass(frozen=True)
class ChildTaskCreateRecord:
    id: str
    goal_id: str
    parent_task_id: str
    assigned_agent_id: str
    title: str
    input_text: str
    priority: int
    depth: int


@dataclass(frozen=True)
class TaskInspectionRecord:
    id: str
    goal_id: str
    parent_task_id: str | None
    assigned_agent_id: str
    title: str
    input_text: str
    result_text: str | None
    status: str
    priority: int
    depth: int
    created_at: str
    started_at: str | None
    completed_at: str | None
    updated_at: str


@dataclass(frozen=True)
class RunInspectionRecord:
    id: str
    task_id: str
    agent_id: str
    attempt_number: int
    status: str
    session_id: str | None
    pid: int | None
    exit_code: int | None
    error_text: str | None
    log_path: str
    usage_json: str | None
    started_at: str | None
    finished_at: str | None
    created_at: str


def bootstrap_database(db_path: PathLike) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.commit()
    finally:
        connection.close()


def connect_database(db_path: PathLike) -> sqlite3.Connection:
    bootstrap_database(db_path)
    connection = sqlite3.connect(Path(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def connect_readonly_database(db_path: PathLike) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise ValueError("database not found")

    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_group(db_path: PathLike, name: str) -> GroupRecord:
    group_name = name.strip()
    if not group_name:
        raise ValueError("group name must not be empty")

    timestamp = _utc_now()
    group_id = str(uuid4())

    connection = connect_database(db_path)
    try:
        connection.execute(
            """
            INSERT INTO groups (id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (group_id, group_name, timestamp, timestamp),
        )
        connection.commit()
    finally:
        connection.close()

    return GroupRecord(
        id=group_id,
        name=group_name,
        created_at=timestamp,
        updated_at=timestamp,
    )


def list_groups(db_path: PathLike) -> list[GroupRecord]:
    connection = connect_database(db_path)
    try:
        rows = connection.execute(
            """
            SELECT id, name, created_at, updated_at
            FROM groups
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()
    finally:
        connection.close()

    return [GroupRecord(**dict(row)) for row in rows]


def create_agent(
    db_path: PathLike,
    *,
    group_name_or_id: str,
    name: str,
    role: str,
    hermes_home: str,
    workdir: str,
    profile_name: str | None = None,
    model_override: str | None = None,
    provider_override: str | None = None,
) -> AgentRecord:
    group_ref = group_name_or_id.strip()
    agent_name = name.strip()
    agent_role = role.strip()
    agent_hermes_home = hermes_home.strip()
    agent_workdir = workdir.strip()

    if not group_ref:
        raise ValueError("group is required")
    if not agent_name:
        raise ValueError("agent name must not be empty")
    if agent_role not in {"lead", "worker"}:
        raise ValueError("agent role must be lead or worker")
    if not agent_hermes_home:
        raise ValueError("hermes home must not be empty")
    if not agent_workdir:
        raise ValueError("workdir must not be empty")

    connection = connect_database(db_path)
    try:
        group_id = _resolve_group_id(connection, group_ref)
        if group_id is None:
            raise ValueError("group not found")
        if agent_role == "lead" and _group_has_lead(connection, group_id):
            raise ValueError("group already has a lead agent")

        timestamp = _utc_now()
        agent_id = str(uuid4())
        normalized_profile_name = _normalize_optional_text(profile_name)
        normalized_model_override = _normalize_optional_text(model_override)
        normalized_provider_override = _normalize_optional_text(provider_override)

        connection.execute(
            """
            INSERT INTO agents (
                id,
                group_id,
                name,
                role,
                profile_name,
                hermes_home,
                workdir,
                model_override,
                provider_override,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                group_id,
                agent_name,
                agent_role,
                normalized_profile_name,
                agent_hermes_home,
                agent_workdir,
                normalized_model_override,
                normalized_provider_override,
                "idle",
                timestamp,
                timestamp,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    return AgentRecord(
        id=agent_id,
        group_id=group_id,
        name=agent_name,
        role=agent_role,
        profile_name=normalized_profile_name,
        hermes_home=agent_hermes_home,
        workdir=agent_workdir,
        model_override=normalized_model_override,
        provider_override=normalized_provider_override,
        status="idle",
        created_at=timestamp,
        updated_at=timestamp,
    )


def submit_goal(
    db_path: PathLike, *, group_name_or_id: str, goal_text: str
) -> GoalSubmissionRecord:
    group_ref = group_name_or_id.strip()
    title = goal_text.strip()

    if not group_ref:
        raise ValueError("group is required")
    if not title:
        raise ValueError("goal text must not be empty")

    connection = connect_database(db_path)
    try:
        group_id = _resolve_group_id(connection, group_ref)
        if group_id is None:
            raise ValueError("group not found")

        lead_agent = _resolve_group_lead_agent(connection, group_id)
        if lead_agent is None:
            raise ValueError("group has no lead agent")

        timestamp = _utc_now()
        goal_id = str(uuid4())
        root_task_id = str(uuid4())

        connection.execute(
            """
            INSERT INTO goals (
                id,
                group_id,
                title,
                status,
                root_task_id,
                started_at,
                completed_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (goal_id, group_id, title, "queued", None, None, None, timestamp, timestamp),
        )
        connection.execute(
            """
            INSERT INTO tasks (
                id,
                goal_id,
                parent_task_id,
                assigned_agent_id,
                title,
                input_text,
                result_text,
                status,
                priority,
                depth,
                created_at,
                started_at,
                completed_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                root_task_id,
                goal_id,
                None,
                lead_agent.id,
                title,
                title,
                None,
                "queued",
                5,
                0,
                timestamp,
                None,
                None,
                timestamp,
            ),
        )
        connection.execute(
            """
            UPDATE goals
            SET root_task_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (root_task_id, timestamp, goal_id),
        )
        connection.commit()
    finally:
        connection.close()

    return GoalSubmissionRecord(
        goal=GoalRecord(
            id=goal_id,
            group_id=group_id,
            title=title,
            status="queued",
            root_task_id=root_task_id,
            started_at=None,
            completed_at=None,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        root_task=TaskRecord(
            id=root_task_id,
            goal_id=goal_id,
            parent_task_id=None,
            assigned_agent_id=lead_agent.id,
            title=title,
            input_text=title,
            result_text=None,
            status="queued",
            priority=5,
            depth=0,
            created_at=timestamp,
            started_at=None,
            completed_at=None,
            updated_at=timestamp,
        ),
    )


def get_goal_status(db_path: PathLike, goal_id: str) -> GoalStatusRecord:
    normalized_goal_id = goal_id.strip()
    if not normalized_goal_id:
        raise ValueError("goal id is required")

    connection = connect_database(db_path)
    try:
        goal_row = connection.execute(
            """
            SELECT id, title, status, root_task_id
            FROM goals
            WHERE id = ?
            """,
            (normalized_goal_id,),
        ).fetchone()
        if goal_row is None:
            raise ValueError("goal not found")

        task_rows = connection.execute(
            """
            SELECT id, assigned_agent_id, title, status, depth
            FROM tasks
            WHERE goal_id = ?
            ORDER BY depth ASC, created_at ASC, id ASC
            """,
            (normalized_goal_id,),
        ).fetchall()
        run_rows = connection.execute(
            """
            SELECT runs.id, runs.task_id, runs.agent_id, runs.attempt_number, runs.status, runs.started_at, runs.finished_at
            FROM runs
            JOIN tasks ON tasks.id = runs.task_id
            WHERE tasks.goal_id = ?
            ORDER BY runs.created_at ASC, runs.id ASC
            """,
            (normalized_goal_id,),
        ).fetchall()
    finally:
        connection.close()

    return GoalStatusRecord(
        id=goal_row["id"],
        title=goal_row["title"],
        status=goal_row["status"],
        root_task_id=goal_row["root_task_id"],
        tasks=[
            GoalStatusTaskRecord(
                id=row["id"],
                assigned_agent_id=row["assigned_agent_id"],
                title=row["title"],
                status=row["status"],
                depth=row["depth"],
            )
            for row in task_rows
        ],
        runs=[
            GoalStatusRunRecord(
                id=row["id"],
                task_id=row["task_id"],
                agent_id=row["agent_id"],
                attempt_number=row["attempt_number"],
                status=row["status"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
            )
            for row in run_rows
        ],
    )


def get_events_for_goal(db_path: PathLike, goal_id: str) -> list[EventRecord]:
    connection = connect_database(db_path)
    try:
        rows = connection.execute(
            """
            SELECT id, goal_id, task_id, run_id, agent_id, event_type, payload_json, created_at
            FROM events
            WHERE goal_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (goal_id,),
        ).fetchall()
    finally:
        connection.close()

    return [EventRecord(**dict(row)) for row in rows]


def get_task_for_inspection(db_path: PathLike, task_id: str) -> TaskInspectionRecord:
    normalized_task_id = task_id.strip()
    if not normalized_task_id:
        raise ValueError("task id is required")

    connection = connect_readonly_database(db_path)
    try:
        row = connection.execute(
            """
            SELECT
                id,
                goal_id,
                parent_task_id,
                assigned_agent_id,
                title,
                input_text,
                result_text,
                status,
                priority,
                depth,
                created_at,
                started_at,
                completed_at,
                updated_at
            FROM tasks
            WHERE id = ?
            """,
            (normalized_task_id,),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
    finally:
        connection.close()

    if row is None:
        raise ValueError("task not found")

    return TaskInspectionRecord(**dict(row))


def get_run_for_inspection(db_path: PathLike, run_id: str) -> RunInspectionRecord:
    normalized_run_id = run_id.strip()
    if not normalized_run_id:
        raise ValueError("run id is required")

    connection = connect_readonly_database(db_path)
    try:
        row = connection.execute(
            """
            SELECT
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
            FROM runs
            WHERE id = ?
            """,
            (normalized_run_id,),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
    finally:
        connection.close()

    if row is None:
        raise ValueError("run not found")

    return RunInspectionRecord(**dict(row))


def resolve_goal_for_start(
    connection: sqlite3.Connection, goal_id: str
) -> tuple[GoalRecord, TaskRecord]:
    normalized_goal_id = goal_id.strip()
    if not normalized_goal_id:
        raise ValueError("goal id is required")

    goal_row = connection.execute(
        """
        SELECT id, group_id, title, status, root_task_id, started_at, completed_at, created_at, updated_at
        FROM goals
        WHERE id = ?
        """,
        (normalized_goal_id,),
    ).fetchone()
    if goal_row is None:
        raise ValueError("goal not found")
    if goal_row["status"] != "queued":
        raise ValueError(f"goal is not startable from state {goal_row['status']}")
    if goal_row["root_task_id"] is None:
        raise ValueError("goal has no root task")

    task_row = connection.execute(
        """
        SELECT
            id,
            goal_id,
            parent_task_id,
            assigned_agent_id,
            title,
            input_text,
            result_text,
            status,
            priority,
            depth,
            created_at,
            started_at,
            completed_at,
            updated_at
        FROM tasks
        WHERE id = ?
        """,
        (goal_row["root_task_id"],),
    ).fetchone()
    if task_row is None:
        raise ValueError("goal root task not found")
    if task_row["status"] != "queued":
        raise ValueError(f"goal is not startable from root task state {task_row['status']}")

    return _goal_from_row(goal_row), _task_from_row(task_row)


def list_queued_tasks_for_goal(connection: sqlite3.Connection, goal_id: str) -> list[TaskRecord]:
    rows = connection.execute(
        """
        SELECT
            id,
            goal_id,
            parent_task_id,
            assigned_agent_id,
            title,
            input_text,
            result_text,
            status,
            priority,
            depth,
            created_at,
            started_at,
            completed_at,
            updated_at
        FROM tasks
        WHERE goal_id = ? AND status = 'queued'
        ORDER BY depth ASC, priority ASC, created_at ASC, id ASC
        """,
        (goal_id,),
    ).fetchall()
    return [_task_from_row(row) for row in rows]


def get_agent_for_task(connection: sqlite3.Connection, task: TaskRecord) -> AgentRecord:
    row = connection.execute(
        """
        SELECT
            agents.id,
            agents.group_id,
            agents.name,
            agents.role,
            agents.profile_name,
            agents.hermes_home,
            agents.workdir,
            agents.model_override,
            agents.provider_override,
            agents.status,
            agents.created_at,
            agents.updated_at
        FROM agents
        JOIN goals ON goals.group_id = agents.group_id
        WHERE goals.id = ? AND agents.id = ?
        """,
        (task.goal_id, task.assigned_agent_id),
    ).fetchone()
    if row is None:
        raise ValueError("assigned agent not found for task")
    return _agent_from_row(row)


def count_active_runs_for_agent(connection: sqlite3.Connection, agent_id: str) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*)
        FROM runs
        WHERE agent_id = ? AND status IN ('queued', 'running')
        """,
        (agent_id,),
    ).fetchone()
    return int(row[0])


def count_non_terminal_tasks_for_goal(connection: sqlite3.Connection, goal_id: str) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*)
        FROM tasks
        WHERE goal_id = ? AND status NOT IN ('complete', 'failed', 'cancelled')
        """,
        (goal_id,),
    ).fetchone()
    return int(row[0])


def next_run_attempt_number(connection: sqlite3.Connection, task_id: str) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(MAX(attempt_number), 0) + 1
        FROM runs
        WHERE task_id = ?
        """,
        (task_id,),
    ).fetchone()
    return int(row[0])


def resolve_group_agent_for_goal(
    connection: sqlite3.Connection, goal_id: str, agent_name_or_id: str
) -> AgentRecord | None:
    row = connection.execute(
        """
        SELECT
            agents.id,
            agents.group_id,
            agents.name,
            agents.role,
            agents.profile_name,
            agents.hermes_home,
            agents.workdir,
            agents.model_override,
            agents.provider_override,
            agents.status,
            agents.created_at,
            agents.updated_at
        FROM agents
        JOIN goals ON goals.group_id = agents.group_id
        WHERE goals.id = ? AND (agents.id = ? OR agents.name = ?)
        ORDER BY CASE WHEN agents.id = ? THEN 0 ELSE 1 END, agents.created_at ASC, agents.id ASC
        LIMIT 1
        """,
        (goal_id, agent_name_or_id, agent_name_or_id, agent_name_or_id),
    ).fetchone()
    if row is None:
        return None
    return _agent_from_row(row)


def create_child_tasks(
    connection: sqlite3.Connection,
    *,
    created_at: str,
    tasks: list[ChildTaskCreateRecord],
) -> list[TaskRecord]:
    created_records: list[TaskRecord] = []
    for child_task in tasks:
        connection.execute(
            """
            INSERT INTO tasks (
                id,
                goal_id,
                parent_task_id,
                assigned_agent_id,
                title,
                input_text,
                result_text,
                status,
                priority,
                depth,
                created_at,
                started_at,
                completed_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                child_task.id,
                child_task.goal_id,
                child_task.parent_task_id,
                child_task.assigned_agent_id,
                child_task.title,
                child_task.input_text,
                None,
                "queued",
                child_task.priority,
                child_task.depth,
                created_at,
                None,
                None,
                created_at,
            ),
        )
        created_records.append(
            TaskRecord(
                id=child_task.id,
                goal_id=child_task.goal_id,
                parent_task_id=child_task.parent_task_id,
                assigned_agent_id=child_task.assigned_agent_id,
                title=child_task.title,
                input_text=child_task.input_text,
                result_text=None,
                status="queued",
                priority=child_task.priority,
                depth=child_task.depth,
                created_at=created_at,
                started_at=None,
                completed_at=None,
                updated_at=created_at,
            )
        )
    return created_records


def mark_goal_complete(connection: sqlite3.Connection, goal_id: str, *, completed_at: str) -> None:
    connection.execute(
        """
        UPDATE goals
        SET status = 'complete', completed_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (completed_at, completed_at, goal_id),
    )


def insert_event(
    connection: sqlite3.Connection,
    *,
    goal_id: str | None,
    task_id: str | None,
    run_id: str | None,
    agent_id: str | None,
    event_type: str,
    payload: dict[str, object],
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO events (id, goal_id, task_id, run_id, agent_id, event_type, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            goal_id,
            task_id,
            run_id,
            agent_id,
            event_type,
            json.dumps(payload, sort_keys=True),
            created_at,
        ),
    )


def _resolve_group_id(connection: sqlite3.Connection, group_name_or_id: str) -> str | None:
    row = connection.execute(
        """
        SELECT id
        FROM groups
        WHERE id = ? OR name = ?
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """,
        (group_name_or_id, group_name_or_id),
    ).fetchone()
    if row is None:
        return None
    return str(row["id"])


def _group_has_lead(connection: sqlite3.Connection, group_id: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM agents
        WHERE group_id = ? AND role = 'lead'
        LIMIT 1
        """,
        (group_id,),
    ).fetchone()
    return row is not None


def _resolve_group_lead_agent(
    connection: sqlite3.Connection, group_id: str
) -> AgentRecord | None:
    row = connection.execute(
        """
        SELECT
            id,
            group_id,
            name,
            role,
            profile_name,
            hermes_home,
            workdir,
            model_override,
            provider_override,
            status,
            created_at,
            updated_at
        FROM agents
        WHERE group_id = ? AND role = 'lead'
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """,
        (group_id,),
    ).fetchone()
    if row is None:
        return None
    return _agent_from_row(row)


def _goal_from_row(row: sqlite3.Row) -> GoalRecord:
    return GoalRecord(
        id=row["id"],
        group_id=row["group_id"],
        title=row["title"],
        status=row["status"],
        root_task_id=row["root_task_id"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _task_from_row(row: sqlite3.Row) -> TaskRecord:
    return TaskRecord(
        id=row["id"],
        goal_id=row["goal_id"],
        parent_task_id=row["parent_task_id"],
        assigned_agent_id=row["assigned_agent_id"],
        title=row["title"],
        input_text=row["input_text"],
        result_text=row["result_text"],
        status=row["status"],
        priority=row["priority"],
        depth=row["depth"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        updated_at=row["updated_at"],
    )


def _agent_from_row(row: sqlite3.Row) -> AgentRecord:
    return AgentRecord(
        id=row["id"],
        group_id=row["group_id"],
        name=row["name"],
        role=row["role"],
        profile_name=row["profile_name"],
        hermes_home=row["hermes_home"],
        workdir=row["workdir"],
        model_override=row["model_override"],
        provider_override=row["provider_override"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
