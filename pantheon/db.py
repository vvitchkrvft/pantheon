"""SQLite bootstrap and persistence helpers for Pantheon."""

from __future__ import annotations

import json
import sqlite3
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

PathLike = str | Path
RUN_LOG_PREVIEW_MAX_LINES = 40
RUN_LOG_PREVIEW_MAX_CHARS = 4000

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
class OverviewSummaryRecord:
    group_id: str
    group_name: str
    agent_count: int
    goal_count: int
    task_count: int
    run_count: int
    active_goal_count: int
    active_task_count: int
    active_run_count: int


@dataclass(frozen=True)
class GoalDetailRecord:
    id: str
    group_id: str
    title: str
    status: str
    root_task_id: str | None
    started_at: str | None
    completed_at: str | None
    created_at: str
    updated_at: str
    task_count: int
    run_count: int


@dataclass(frozen=True)
class TaskListItemRecord:
    id: str
    goal_id: str
    assigned_agent_id: str
    title: str
    status: str
    depth: int
    priority: int
    created_at: str
    assigned_agent_name: str
    goal_title: str


@dataclass(frozen=True)
class TaskDetailRecord:
    id: str
    goal_id: str
    parent_task_id: str | None
    assigned_agent_id: str
    assigned_agent_name: str
    goal_title: str
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
class RunListItemRecord:
    id: str
    task_id: str
    agent_id: str
    attempt_number: int
    status: str
    created_at: str
    task_title: str
    agent_name: str


@dataclass(frozen=True)
class RunDetailRecord:
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
    task_title: str
    agent_name: str
    goal_title: str
    log_preview_label: str
    log_preview_text: str


@dataclass(frozen=True)
class CancelGoalResult:
    goal_id: str
    goal_status: str
    queued_task_ids: list[str]
    active_task_ids: list[str]
    active_run_ids: list[str]
    cancelled_at: str


@dataclass(frozen=True)
class RetryTaskResult:
    task_id: str
    goal_id: str
    task_status: str
    goal_status: str
    retried_at: str


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
    task_title: str
    agent_name: str
    goal_title: str
    log_preview_label: str
    log_preview_text: str


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


def _build_run_log_preview(log_path: PathLike) -> tuple[str, str]:
    path = Path(log_path)
    if not path.exists():
        return ("missing", f"Log preview unavailable: file not found at {path}")

    text = path.read_text(encoding="utf-8", errors="replace")
    if text == "":
        return ("empty", "Log preview unavailable: log file is empty.")

    lines = text.splitlines()
    if not lines:
        return ("empty", "Log preview unavailable: log file is empty.")

    tail_lines: deque[str] = deque()
    char_count = 0
    for line in reversed(lines):
        separator_width = 1 if tail_lines else 0
        line_width = len(line)
        if tail_lines and (len(tail_lines) >= RUN_LOG_PREVIEW_MAX_LINES or char_count + separator_width + line_width > RUN_LOG_PREVIEW_MAX_CHARS):
            break
        if not tail_lines and line_width > RUN_LOG_PREVIEW_MAX_CHARS:
            tail_lines.appendleft(line[-RUN_LOG_PREVIEW_MAX_CHARS :])
            char_count = len(tail_lines[0])
            break
        tail_lines.appendleft(line)
        char_count += separator_width + line_width

    preview_text = "\n".join(tail_lines)
    clipped = len(tail_lines) < len(lines) or len(preview_text) < len(text.rstrip("\n"))
    if clipped:
        return (
            f"tail preview (last {RUN_LOG_PREVIEW_MAX_LINES} lines / {RUN_LOG_PREVIEW_MAX_CHARS} chars max)",
            preview_text,
        )
    return ("full preview", preview_text)


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


def resolve_current_group_id(db_path: PathLike) -> str | None:
    groups = list_groups(db_path)
    if not groups:
        return None
    return groups[0].id


def get_group_for_tui(db_path: PathLike, group_id: str) -> GroupRecord:
    normalized_group_id = group_id.strip()
    if not normalized_group_id:
        raise ValueError("group id is required")

    connection = connect_readonly_database(db_path)
    try:
        row = connection.execute(
            """
            SELECT id, name, created_at, updated_at
            FROM groups
            WHERE id = ?
            """,
            (normalized_group_id,),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
    finally:
        connection.close()

    if row is None:
        raise ValueError("group not found")

    return GroupRecord(**dict(row))


def get_overview_summary(db_path: PathLike, group_id: str) -> OverviewSummaryRecord:
    normalized_group_id = group_id.strip()
    if not normalized_group_id:
        raise ValueError("group id is required")

    connection = connect_readonly_database(db_path)
    try:
        row = connection.execute(
            """
            SELECT
                groups.id AS group_id,
                groups.name AS group_name,
                (
                    SELECT COUNT(*)
                    FROM agents
                    WHERE agents.group_id = groups.id
                ) AS agent_count,
                (
                    SELECT COUNT(*)
                    FROM goals
                    WHERE goals.group_id = groups.id
                ) AS goal_count,
                (
                    SELECT COUNT(*)
                    FROM tasks
                    JOIN goals ON goals.id = tasks.goal_id
                    WHERE goals.group_id = groups.id
                ) AS task_count,
                (
                    SELECT COUNT(*)
                    FROM runs
                    JOIN tasks ON tasks.id = runs.task_id
                    JOIN goals ON goals.id = tasks.goal_id
                    WHERE goals.group_id = groups.id
                ) AS run_count,
                (
                    SELECT COUNT(*)
                    FROM goals
                    WHERE goals.group_id = groups.id
                      AND goals.status IN ('queued', 'running')
                ) AS active_goal_count,
                (
                    SELECT COUNT(*)
                    FROM tasks
                    JOIN goals ON goals.id = tasks.goal_id
                    WHERE goals.group_id = groups.id
                      AND tasks.status IN ('queued', 'running')
                ) AS active_task_count,
                (
                    SELECT COUNT(*)
                    FROM runs
                    JOIN tasks ON tasks.id = runs.task_id
                    JOIN goals ON goals.id = tasks.goal_id
                    WHERE goals.group_id = groups.id
                      AND runs.status IN ('queued', 'running')
                ) AS active_run_count
            FROM groups
            WHERE groups.id = ?
            """,
            (normalized_group_id,),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
    finally:
        connection.close()

    if row is None:
        raise ValueError("group not found")

    return OverviewSummaryRecord(**dict(row))


def list_agents_for_group(db_path: PathLike, group_id: str) -> list[AgentRecord]:
    normalized_group_id = group_id.strip()
    if not normalized_group_id:
        raise ValueError("group id is required")

    connection = connect_readonly_database(db_path)
    try:
        rows = connection.execute(
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
            WHERE group_id = ?
            ORDER BY CASE role WHEN 'lead' THEN 0 ELSE 1 END, name ASC, id ASC
            """,
            (normalized_group_id,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
    finally:
        connection.close()

    return [AgentRecord(**dict(row)) for row in rows]


def get_agent_for_tui(db_path: PathLike, agent_id: str) -> AgentRecord:
    normalized_agent_id = agent_id.strip()
    if not normalized_agent_id:
        raise ValueError("agent id is required")

    connection = connect_readonly_database(db_path)
    try:
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
            WHERE id = ?
            """,
            (normalized_agent_id,),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
    finally:
        connection.close()

    if row is None:
        raise ValueError("agent not found")

    return AgentRecord(**dict(row))


def list_goals_for_group(db_path: PathLike, group_id: str) -> list[GoalDetailRecord]:
    normalized_group_id = group_id.strip()
    if not normalized_group_id:
        raise ValueError("group id is required")

    connection = connect_readonly_database(db_path)
    try:
        rows = connection.execute(
            """
            SELECT
                goals.id,
                goals.group_id,
                goals.title,
                goals.status,
                goals.root_task_id,
                goals.started_at,
                goals.completed_at,
                goals.created_at,
                goals.updated_at,
                COUNT(DISTINCT tasks.id) AS task_count,
                COUNT(DISTINCT runs.id) AS run_count
            FROM goals
            LEFT JOIN tasks ON tasks.goal_id = goals.id
            LEFT JOIN runs ON runs.task_id = tasks.id
            WHERE goals.group_id = ?
            GROUP BY goals.id
            ORDER BY goals.created_at ASC, goals.id ASC
            """,
            (normalized_group_id,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
    finally:
        connection.close()

    return [GoalDetailRecord(**dict(row)) for row in rows]


def get_goal_for_tui(db_path: PathLike, goal_id: str) -> GoalDetailRecord:
    normalized_goal_id = goal_id.strip()
    if not normalized_goal_id:
        raise ValueError("goal id is required")

    connection = connect_readonly_database(db_path)
    try:
        row = connection.execute(
            """
            SELECT
                goals.id,
                goals.group_id,
                goals.title,
                goals.status,
                goals.root_task_id,
                goals.started_at,
                goals.completed_at,
                goals.created_at,
                goals.updated_at,
                COUNT(DISTINCT tasks.id) AS task_count,
                COUNT(DISTINCT runs.id) AS run_count
            FROM goals
            LEFT JOIN tasks ON tasks.goal_id = goals.id
            LEFT JOIN runs ON runs.task_id = tasks.id
            WHERE goals.id = ?
            GROUP BY goals.id
            """,
            (normalized_goal_id,),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
    finally:
        connection.close()

    if row is None:
        raise ValueError("goal not found")

    return GoalDetailRecord(**dict(row))


def list_tasks_for_group(db_path: PathLike, group_id: str) -> list[TaskListItemRecord]:
    normalized_group_id = group_id.strip()
    if not normalized_group_id:
        raise ValueError("group id is required")

    connection = connect_readonly_database(db_path)
    try:
        rows = connection.execute(
            """
            SELECT
                tasks.id,
                tasks.goal_id,
                tasks.assigned_agent_id,
                tasks.title,
                tasks.status,
                tasks.depth,
                tasks.priority,
                tasks.created_at,
                agents.name AS assigned_agent_name,
                goals.title AS goal_title
            FROM tasks
            JOIN agents ON agents.id = tasks.assigned_agent_id
            JOIN goals ON goals.id = tasks.goal_id
            WHERE goals.group_id = ?
            ORDER BY tasks.depth ASC, tasks.priority ASC, tasks.created_at ASC, tasks.id ASC
            """,
            (normalized_group_id,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
    finally:
        connection.close()

    return [TaskListItemRecord(**dict(row)) for row in rows]


def get_task_for_tui(db_path: PathLike, task_id: str) -> TaskDetailRecord:
    normalized_task_id = task_id.strip()
    if not normalized_task_id:
        raise ValueError("task id is required")

    connection = connect_readonly_database(db_path)
    try:
        row = connection.execute(
            """
            SELECT
                tasks.id,
                tasks.goal_id,
                tasks.parent_task_id,
                tasks.assigned_agent_id,
                agents.name AS assigned_agent_name,
                goals.title AS goal_title,
                tasks.title,
                tasks.input_text,
                tasks.result_text,
                tasks.status,
                tasks.priority,
                tasks.depth,
                tasks.created_at,
                tasks.started_at,
                tasks.completed_at,
                tasks.updated_at
            FROM tasks
            JOIN agents ON agents.id = tasks.assigned_agent_id
            JOIN goals ON goals.id = tasks.goal_id
            WHERE tasks.id = ?
            """,
            (normalized_task_id,),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
    finally:
        connection.close()

    if row is None:
        raise ValueError("task not found")

    return TaskDetailRecord(**dict(row))


def list_runs_for_group(db_path: PathLike, group_id: str) -> list[RunListItemRecord]:
    normalized_group_id = group_id.strip()
    if not normalized_group_id:
        raise ValueError("group id is required")

    connection = connect_readonly_database(db_path)
    try:
        rows = connection.execute(
            """
            SELECT
                runs.id,
                runs.task_id,
                runs.agent_id,
                runs.attempt_number,
                runs.status,
                runs.created_at,
                tasks.title AS task_title,
                agents.name AS agent_name
            FROM runs
            JOIN tasks ON tasks.id = runs.task_id
            JOIN goals ON goals.id = tasks.goal_id
            JOIN agents ON agents.id = runs.agent_id
            WHERE goals.group_id = ?
            ORDER BY runs.created_at ASC, runs.id ASC
            """,
            (normalized_group_id,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
    finally:
        connection.close()

    return [RunListItemRecord(**dict(row)) for row in rows]


def get_run_for_tui(db_path: PathLike, run_id: str) -> RunDetailRecord:
    normalized_run_id = run_id.strip()
    if not normalized_run_id:
        raise ValueError("run id is required")

    connection = connect_readonly_database(db_path)
    try:
        row = connection.execute(
            """
            SELECT
                runs.id,
                runs.task_id,
                runs.agent_id,
                runs.attempt_number,
                runs.status,
                runs.session_id,
                runs.pid,
                runs.exit_code,
                runs.error_text,
                runs.log_path,
                runs.usage_json,
                runs.started_at,
                runs.finished_at,
                runs.created_at,
                COALESCE(tasks.title, runs.task_id) AS task_title,
                COALESCE(agents.name, runs.agent_id) AS agent_name,
                COALESCE(goals.title, tasks.goal_id, 'unknown goal') AS goal_title
            FROM runs
            LEFT JOIN tasks ON tasks.id = runs.task_id
            LEFT JOIN goals ON goals.id = tasks.goal_id
            LEFT JOIN agents ON agents.id = runs.agent_id
            WHERE runs.id = ?
            """,
            (normalized_run_id,),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
    finally:
        connection.close()

    if row is None:
        raise ValueError("run not found")

    log_preview_label, log_preview_text = _build_run_log_preview(row["log_path"])
    return RunDetailRecord(
        **dict(row),
        log_preview_label=log_preview_label,
        log_preview_text=log_preview_text,
    )


def get_recent_events_for_group(
    db_path: PathLike,
    group_id: str,
    *,
    limit: int = 10,
) -> list[EventRecord]:
    normalized_group_id = group_id.strip()
    if not normalized_group_id:
        raise ValueError("group id is required")
    if limit <= 0:
        raise ValueError("limit must be positive")

    connection = connect_readonly_database(db_path)
    try:
        rows = connection.execute(
            """
            SELECT
                events.id,
                events.goal_id,
                events.task_id,
                events.run_id,
                events.agent_id,
                events.event_type,
                events.payload_json,
                events.created_at
            FROM events
            JOIN goals ON goals.id = events.goal_id
            WHERE goals.group_id = ?
            ORDER BY events.created_at DESC, events.rowid DESC
            LIMIT ?
            """,
            (normalized_group_id, limit),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
    finally:
        connection.close()

    return [EventRecord(**dict(row)) for row in rows]


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
    normalized_goal_id = goal_id.strip()
    if not normalized_goal_id:
        raise ValueError("goal id is required")

    connection = connect_readonly_database(db_path)
    try:
        goal_exists = connection.execute(
            """
            SELECT 1
            FROM goals
            WHERE id = ?
            """,
            (normalized_goal_id,),
        ).fetchone()
        if goal_exists is None:
            raise ValueError("goal not found")
        rows = connection.execute(
            """
            SELECT id, goal_id, task_id, run_id, agent_id, event_type, payload_json, created_at
            FROM events
            WHERE goal_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (normalized_goal_id,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
    finally:
        connection.close()

    return [EventRecord(**dict(row)) for row in rows]


def get_events_for_task(db_path: PathLike, task_id: str) -> list[EventRecord]:
    normalized_task_id = task_id.strip()
    if not normalized_task_id:
        raise ValueError("task id is required")

    connection = connect_readonly_database(db_path)
    try:
        task_exists = connection.execute(
            """
            SELECT 1
            FROM tasks
            WHERE id = ?
            """,
            (normalized_task_id,),
        ).fetchone()
        if task_exists is None:
            raise ValueError("task not found")
        rows = connection.execute(
            """
            SELECT id, goal_id, task_id, run_id, agent_id, event_type, payload_json, created_at
            FROM events
            WHERE task_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (normalized_task_id,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
    finally:
        connection.close()

    return [EventRecord(**dict(row)) for row in rows]


def get_events_for_run(db_path: PathLike, run_id: str) -> list[EventRecord]:
    normalized_run_id = run_id.strip()
    if not normalized_run_id:
        raise ValueError("run id is required")

    connection = connect_readonly_database(db_path)
    try:
        run_exists = connection.execute(
            """
            SELECT 1
            FROM runs
            WHERE id = ?
            """,
            (normalized_run_id,),
        ).fetchone()
        if run_exists is None:
            raise ValueError("run not found")
        rows = connection.execute(
            """
            SELECT id, goal_id, task_id, run_id, agent_id, event_type, payload_json, created_at
            FROM events
            WHERE run_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (normalized_run_id,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
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
                runs.id,
                runs.task_id,
                runs.agent_id,
                runs.attempt_number,
                runs.status,
                runs.session_id,
                runs.pid,
                runs.exit_code,
                runs.error_text,
                runs.log_path,
                runs.usage_json,
                runs.started_at,
                runs.finished_at,
                runs.created_at,
                COALESCE(tasks.title, runs.task_id) AS task_title,
                COALESCE(agents.name, runs.agent_id) AS agent_name,
                COALESCE(goals.title, tasks.goal_id, 'unknown goal') AS goal_title
            FROM runs
            LEFT JOIN tasks ON tasks.id = runs.task_id
            LEFT JOIN goals ON goals.id = tasks.goal_id
            LEFT JOIN agents ON agents.id = runs.agent_id
            WHERE runs.id = ?
            """,
            (normalized_run_id,),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        raise ValueError("database is not initialized") from exc
    finally:
        connection.close()

    if row is None:
        raise ValueError("run not found")

    log_preview_label, log_preview_text = _build_run_log_preview(row["log_path"])
    return RunInspectionRecord(
        **dict(row),
        log_preview_label=log_preview_label,
        log_preview_text=log_preview_text,
    )


def cancel_goal(db_path: PathLike, goal_id: str) -> CancelGoalResult:
    normalized_goal_id = goal_id.strip()
    if not normalized_goal_id:
        raise ValueError("goal id is required")

    connection = connect_database(db_path)
    try:
        goal_row = connection.execute(
            """
            SELECT id, status
            FROM goals
            WHERE id = ?
            """,
            (normalized_goal_id,),
        ).fetchone()
        if goal_row is None:
            raise ValueError("goal not found")

        goal_status = str(goal_row["status"])
        if goal_status not in {"queued", "running"}:
            raise ValueError(f"goal is not cancellable from state {goal_status}")

        cancelled_at = _utc_now()
        queued_task_rows = connection.execute(
            """
            SELECT id, assigned_agent_id
            FROM tasks
            WHERE goal_id = ? AND status = 'queued'
            ORDER BY depth ASC, created_at ASC, id ASC
            """,
            (normalized_goal_id,),
        ).fetchall()
        active_task_rows = connection.execute(
            """
            SELECT id, assigned_agent_id
            FROM tasks
            WHERE goal_id = ? AND status = 'running'
            ORDER BY depth ASC, created_at ASC, id ASC
            """,
            (normalized_goal_id,),
        ).fetchall()
        active_run_rows = connection.execute(
            """
            SELECT runs.id, runs.task_id, runs.agent_id, runs.status
            FROM runs
            JOIN tasks ON tasks.id = runs.task_id
            WHERE tasks.goal_id = ? AND runs.status IN ('queued', 'running')
            ORDER BY runs.created_at ASC, runs.id ASC
            """,
            (normalized_goal_id,),
        ).fetchall()

        connection.execute(
            """
            UPDATE goals
            SET status = 'cancelled',
                completed_at = COALESCE(completed_at, ?),
                updated_at = ?
            WHERE id = ?
            """,
            (cancelled_at, cancelled_at, normalized_goal_id),
        )
        connection.execute(
            """
            UPDATE tasks
            SET status = 'cancelled',
                completed_at = ?,
                updated_at = ?
            WHERE goal_id = ? AND status = 'queued'
            """,
            (cancelled_at, cancelled_at, normalized_goal_id),
        )

        insert_event(
            connection,
            goal_id=normalized_goal_id,
            task_id=None,
            run_id=None,
            agent_id=None,
            event_type="goal.cancelled",
            payload={
                "goal_id": normalized_goal_id,
                "status": "cancelled",
                "queued_task_count": len(queued_task_rows),
                "active_task_count": len(active_task_rows),
                "active_run_count": len(active_run_rows),
                "runtime_cancellation_supported": False,
            },
            created_at=cancelled_at,
        )
        for task_row in queued_task_rows:
            insert_event(
                connection,
                goal_id=normalized_goal_id,
                task_id=str(task_row["id"]),
                run_id=None,
                agent_id=str(task_row["assigned_agent_id"]),
                event_type="task.cancelled",
                payload={"task_id": str(task_row["id"]), "status": "cancelled"},
                created_at=cancelled_at,
            )
        for run_row in active_run_rows:
            insert_event(
                connection,
                goal_id=normalized_goal_id,
                task_id=str(run_row["task_id"]),
                run_id=str(run_row["id"]),
                agent_id=str(run_row["agent_id"]),
                event_type="run.cancellation_requested",
                payload={
                    "run_id": str(run_row["id"]),
                    "task_id": str(run_row["task_id"]),
                    "status": str(run_row["status"]),
                    "runtime_cancellation_supported": False,
                },
                created_at=cancelled_at,
            )
        connection.commit()
    finally:
        connection.close()

    return CancelGoalResult(
        goal_id=normalized_goal_id,
        goal_status="cancelled",
        queued_task_ids=[str(row["id"]) for row in queued_task_rows],
        active_task_ids=[str(row["id"]) for row in active_task_rows],
        active_run_ids=[str(row["id"]) for row in active_run_rows],
        cancelled_at=cancelled_at,
    )


def retry_task(db_path: PathLike, task_id: str) -> RetryTaskResult:
    normalized_task_id = task_id.strip()
    if not normalized_task_id:
        raise ValueError("task id is required")

    connection = connect_database(db_path)
    try:
        task_row = connection.execute(
            """
            SELECT id, goal_id, assigned_agent_id, status
            FROM tasks
            WHERE id = ?
            """,
            (normalized_task_id,),
        ).fetchone()
        if task_row is None:
            raise ValueError("task not found")

        task_status = str(task_row["status"])
        if task_status not in {"failed", "cancelled"}:
            raise ValueError(f"task is not retryable from state {task_status}")

        active_run_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM runs
            WHERE task_id = ? AND status IN ('queued', 'running')
            """,
            (normalized_task_id,),
        ).fetchone()
        if active_run_count is not None and int(active_run_count[0]) > 0:
            raise ValueError("task already has an active run")

        goal_row = connection.execute(
            """
            SELECT id, status
            FROM goals
            WHERE id = ?
            """,
            (str(task_row["goal_id"]),),
        ).fetchone()
        if goal_row is None:
            raise ValueError("goal not found for task")

        goal_status = str(goal_row["status"])
        if goal_status == "complete":
            raise ValueError("task cannot be retried because goal is complete")
        if goal_status not in {"queued", "running", "cancelled"}:
            raise ValueError(f"task cannot be retried from goal state {goal_status}")

        retried_at = _utc_now()
        next_goal_status = "queued" if goal_status == "cancelled" else goal_status

        connection.execute(
            """
            UPDATE tasks
            SET status = 'queued',
                result_text = NULL,
                completed_at = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (retried_at, normalized_task_id),
        )
        connection.execute(
            """
            UPDATE goals
            SET status = ?,
                completed_at = CASE WHEN ? = 'queued' THEN NULL ELSE completed_at END,
                updated_at = ?
            WHERE id = ?
            """,
            (next_goal_status, next_goal_status, retried_at, str(task_row["goal_id"])),
        )
        insert_event(
            connection,
            goal_id=str(task_row["goal_id"]),
            task_id=normalized_task_id,
            run_id=None,
            agent_id=str(task_row["assigned_agent_id"]),
            event_type="task.retried",
            payload={
                "task_id": normalized_task_id,
                "from_status": task_status,
                "status": "queued",
                "goal_status": next_goal_status,
            },
            created_at=retried_at,
        )
        connection.commit()
    finally:
        connection.close()

    return RetryTaskResult(
        task_id=normalized_task_id,
        goal_id=str(task_row["goal_id"]),
        task_status="queued",
        goal_status=next_goal_status,
        retried_at=retried_at,
    )


def resolve_goal_for_start(
    connection: sqlite3.Connection, goal_id: str
) -> GoalRecord:
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
    if goal_row["status"] not in {"queued", "running"}:
        raise ValueError(f"goal is not startable from state {goal_row['status']}")
    if goal_row["status"] == "queued" and goal_row["root_task_id"] is None:
        raise ValueError("goal has no root task")
    if goal_row["root_task_id"] is not None:
        task_row = connection.execute(
            """
            SELECT status
            FROM tasks
            WHERE id = ?
            """,
            (goal_row["root_task_id"],),
        ).fetchone()
        if task_row is None:
            raise ValueError("goal root task not found")
        if goal_row["status"] == "queued" and task_row["status"] != "queued":
            raise ValueError(
                f"goal is not startable from root task state {task_row['status']}"
            )

    return _goal_from_row(goal_row)


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
