import sqlite3
from pathlib import Path

import pytest

from pantheon.db import bootstrap_database, create_agent, create_group, submit_goal


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


def test_create_agent_persists_agent_row(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    group = create_group(db_path, "research")

    agent = create_agent(
        db_path,
        group_name_or_id=group.name,
        name="lead-1",
        role="lead",
        hermes_home="/tmp/hermes-home",
        workdir="/tmp/workdir",
    )

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT id, group_id, name, role, profile_name, hermes_home, workdir, status
            FROM agents
            """
        ).fetchone()
    finally:
        connection.close()

    assert row == (
        agent.id,
        group.id,
        "lead-1",
        "lead",
        None,
        "/tmp/hermes-home",
        "/tmp/workdir",
        "idle",
    )


def test_create_agent_rejects_second_lead_in_group(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    group = create_group(db_path, "research")
    create_agent(
        db_path,
        group_name_or_id=group.id,
        name="lead-1",
        role="lead",
        hermes_home="/tmp/hermes-home-1",
        workdir="/tmp/workdir-1",
    )

    with pytest.raises(ValueError, match="group already has a lead agent"):
        create_agent(
            db_path,
            group_name_or_id=group.id,
            name="lead-2",
            role="lead",
            hermes_home="/tmp/hermes-home-2",
            workdir="/tmp/workdir-2",
        )


def test_submit_goal_creates_goal_and_root_task_for_group_lead(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    group = create_group(db_path, "research")
    lead = create_agent(
        db_path,
        group_name_or_id=group.id,
        name="lead-1",
        role="lead",
        hermes_home="/tmp/hermes-home",
        workdir="/tmp/workdir",
    )

    submission = submit_goal(
        db_path,
        group_name_or_id=group.name,
        goal_text="Ship the first Pantheon slice",
    )

    assert submission.goal.group_id == group.id
    assert submission.goal.title == "Ship the first Pantheon slice"
    assert submission.goal.status == "queued"
    assert submission.goal.root_task_id == submission.root_task.id
    assert submission.root_task.goal_id == submission.goal.id
    assert submission.root_task.assigned_agent_id == lead.id
    assert submission.root_task.title == "Ship the first Pantheon slice"
    assert submission.root_task.input_text == "Ship the first Pantheon slice"
    assert submission.root_task.status == "queued"
    assert submission.root_task.depth == 0

    connection = sqlite3.connect(db_path)
    try:
        goal_row = connection.execute(
            """
            SELECT id, group_id, title, status, root_task_id
            FROM goals
            """
        ).fetchone()
        task_row = connection.execute(
            """
            SELECT id, goal_id, parent_task_id, assigned_agent_id, title, input_text, status, depth
            FROM tasks
            """
        ).fetchone()
    finally:
        connection.close()

    assert goal_row == (
        submission.goal.id,
        group.id,
        "Ship the first Pantheon slice",
        "queued",
        submission.root_task.id,
    )
    assert task_row == (
        submission.root_task.id,
        submission.goal.id,
        None,
        lead.id,
        "Ship the first Pantheon slice",
        "Ship the first Pantheon slice",
        "queued",
        0,
    )


def test_submit_goal_rejects_missing_group(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    with pytest.raises(ValueError, match="group not found"):
        submit_goal(
            db_path,
            group_name_or_id="missing",
            goal_text="Ship the first Pantheon slice",
        )


def test_submit_goal_rejects_group_without_lead(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    group = create_group(db_path, "research")
    create_agent(
        db_path,
        group_name_or_id=group.id,
        name="worker-1",
        role="worker",
        hermes_home="/tmp/hermes-home",
        workdir="/tmp/workdir",
    )

    with pytest.raises(ValueError, match="group has no lead agent"):
        submit_goal(
            db_path,
            group_name_or_id=group.name,
            goal_text="Ship the first Pantheon slice",
        )
