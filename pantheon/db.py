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
class GoalStatusRecord:
    id: str
    title: str
    status: str
    root_task_id: str | None
    tasks: list[GoalStatusTaskRecord]


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
