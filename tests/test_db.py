import sqlite3
from pathlib import Path

from pantheon.db import bootstrap_database


EXPECTED_TABLE_COLUMNS = {
    "groups": ["id", "name", "created_at", "updated_at"],
    "agents": [
        "id",
        "group_id",
        "name",
        "role",
        "profile_name",
        "hermes_home",
        "workdir",
        "model_override",
        "provider_override",
        "status",
        "created_at",
        "updated_at",
    ],
    "goals": [
        "id",
        "group_id",
        "title",
        "status",
        "root_task_id",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    ],
    "tasks": [
        "id",
        "goal_id",
        "parent_task_id",
        "assigned_agent_id",
        "title",
        "input_text",
        "result_text",
        "status",
        "priority",
        "depth",
        "created_at",
        "started_at",
        "completed_at",
        "updated_at",
    ],
    "runs": [
        "id",
        "task_id",
        "agent_id",
        "attempt_number",
        "status",
        "session_id",
        "pid",
        "exit_code",
        "error_text",
        "log_path",
        "usage_json",
        "started_at",
        "finished_at",
        "created_at",
    ],
    "events": [
        "id",
        "goal_id",
        "task_id",
        "run_id",
        "agent_id",
        "event_type",
        "payload_json",
        "created_at",
    ],
}

EXPECTED_FOREIGN_KEYS = {
    "agents": {("group_id", "groups", "id", "CASCADE")},
    "goals": {
        ("group_id", "groups", "id", "CASCADE"),
        ("root_task_id", "tasks", "id", "SET NULL"),
    },
    "tasks": {
        ("goal_id", "goals", "id", "CASCADE"),
        ("parent_task_id", "tasks", "id", "RESTRICT"),
        ("assigned_agent_id", "agents", "id", "RESTRICT"),
    },
    "runs": {
        ("task_id", "tasks", "id", "CASCADE"),
        ("agent_id", "agents", "id", "RESTRICT"),
    },
    "events": {
        ("goal_id", "goals", "id", "CASCADE"),
        ("task_id", "tasks", "id", "CASCADE"),
        ("run_id", "runs", "id", "CASCADE"),
        ("agent_id", "agents", "id", "CASCADE"),
    },
}

EXPECTED_INDEXES = {
    "idx_agents_group_id",
    "idx_goals_group_id",
    "idx_tasks_goal_id",
    "idx_tasks_parent_task_id",
    "idx_tasks_assigned_agent_status",
    "idx_tasks_goal_status",
    "idx_tasks_dispatch_order",
    "idx_runs_task_id",
    "idx_runs_agent_id_status",
    "idx_events_goal_created_at",
    "idx_events_task_created_at",
    "idx_events_run_created_at",
}


def _table_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [row[1] for row in rows]


def _foreign_keys(
    connection: sqlite3.Connection, table_name: str
) -> set[tuple[str, str, str, str]]:
    rows = connection.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
    return {(row[3], row[2], row[4], row[6]) for row in rows}


def test_bootstrap_database_creates_v1_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    bootstrap_database(db_path)

    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row[0] for row in rows}
        assert set(EXPECTED_TABLE_COLUMNS) <= table_names

        for table_name, expected_columns in EXPECTED_TABLE_COLUMNS.items():
            assert _table_columns(connection, table_name) == expected_columns

        for table_name, expected_foreign_keys in EXPECTED_FOREIGN_KEYS.items():
            assert _foreign_keys(connection, table_name) == expected_foreign_keys

        index_rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        index_names = {row[0] for row in index_rows}
        assert EXPECTED_INDEXES <= index_names
    finally:
        connection.close()


def test_bootstrap_database_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    bootstrap_database(db_path)

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO groups (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("group-1", "alpha", "2026-04-15T00:00:00Z", "2026-04-15T00:00:00Z"),
        )
        connection.commit()
    finally:
        connection.close()

    bootstrap_database(db_path)

    verification = sqlite3.connect(db_path)
    try:
        row = verification.execute("SELECT id, name FROM groups").fetchone()
    finally:
        verification.close()

    assert row == ("group-1", "alpha")
