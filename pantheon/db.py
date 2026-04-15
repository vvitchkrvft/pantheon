"""SQLite bootstrap and persistence helpers for Pantheon."""

from __future__ import annotations

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


@dataclass(frozen=True)
class GroupRecord:
    id: str
    name: str
    created_at: str
    updated_at: str


def connect_database(db_path: PathLike) -> sqlite3.Connection:
    bootstrap_database(db_path)
    connection = sqlite3.connect(Path(db_path))
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

    return [
        GroupRecord(
            id=row["id"],
            name=row["name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
