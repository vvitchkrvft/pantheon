import sqlite3
from pathlib import Path

import pytest

from pantheon.adapters import HermesAdapter
from pantheon.db import (
    bootstrap_database,
    create_agent,
    create_group,
    get_events_for_goal,
    get_goal_status,
    submit_goal,
)
from pantheon.runner import start_goal_execution


class RaisingAdapter(HermesAdapter):
    def run_task(self, agent, task, run_context):  # type: ignore[override]
        raise RuntimeError("adapter exploded")


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


def test_get_goal_status_returns_goal_summary_and_tasks(tmp_path: Path) -> None:
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
        group_name_or_id=group.id,
        goal_text="Ship the first Pantheon slice",
    )

    connection = sqlite3.connect(db_path)
    try:
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
                "task-child-1",
                submission.goal.id,
                submission.root_task.id,
                lead.id,
                "Review outputs",
                "Review outputs",
                None,
                "running",
                5,
                1,
                "2026-04-15T00:00:01Z",
                None,
                None,
                "2026-04-15T00:00:01Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    status = get_goal_status(db_path, submission.goal.id)

    assert status.id == submission.goal.id
    assert status.title == "Ship the first Pantheon slice"
    assert status.status == "queued"
    assert status.root_task_id == submission.root_task.id
    assert status.tasks == [
        type(status.tasks[0])(
            id=submission.root_task.id,
            assigned_agent_id=lead.id,
            title="Ship the first Pantheon slice",
            status="queued",
            depth=0,
        ),
        type(status.tasks[0])(
            id="task-child-1",
            assigned_agent_id=lead.id,
            title="Review outputs",
            status="running",
            depth=1,
        ),
    ]
    assert status.runs == []


def test_get_goal_status_rejects_missing_goal(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    with pytest.raises(ValueError, match="goal not found"):
        get_goal_status(db_path, "missing-goal")


def test_start_goal_execution_persists_first_run_and_terminal_transitions(
    tmp_path: Path,
) -> None:
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
        group_name_or_id=group.id,
        goal_text="Ship the first Pantheon slice",
    )

    start_result = start_goal_execution(db_path, submission.goal.id)

    assert start_result.goal_id == submission.goal.id
    assert len(start_result.runs) == 1

    run = start_result.runs[0]
    assert run.task_id == submission.root_task.id
    assert run.agent_id == lead.id
    assert run.attempt_number == 1
    assert run.status == "complete"
    assert run.exit_code == 0
    assert run.error_text is None
    assert run.started_at is not None
    assert run.finished_at is not None
    assert run.log_path.endswith(f"{run.id}.log")

    connection = sqlite3.connect(db_path)
    try:
        goal_row = connection.execute(
            """
            SELECT status, started_at, completed_at
            FROM goals
            WHERE id = ?
            """,
            (submission.goal.id,),
        ).fetchone()
        task_row = connection.execute(
            """
            SELECT status, result_text, started_at, completed_at
            FROM tasks
            WHERE id = ?
            """,
            (submission.root_task.id,),
        ).fetchone()
        agent_row = connection.execute(
            """
            SELECT status
            FROM agents
            WHERE id = ?
            """,
            (lead.id,),
        ).fetchone()
        run_row = connection.execute(
            """
            SELECT status, attempt_number, session_id, exit_code, error_text, started_at, finished_at
            FROM runs
            WHERE id = ?
            """,
            (run.id,),
        ).fetchone()
    finally:
        connection.close()

    # Without a lead completion_judgment path, all-complete work remains running by contract.
    assert goal_row == ("running", start_result.started_at, None)
    assert task_row == (
        "complete",
        "stub Hermes execution completed",
        run.started_at,
        run.finished_at,
    )
    assert agent_row == ("idle",)
    assert run_row == (
        "complete",
        1,
        f"stub-session-{run.id}",
        0,
        None,
        run.started_at,
        run.finished_at,
    )

    events = get_events_for_goal(db_path, submission.goal.id)
    assert [event.event_type for event in events] == [
        "goal.started",
        "run.started",
        "task.started",
        "run.output",
        "run.completed",
        "task.completed",
    ]


def test_start_goal_execution_increments_attempt_number_for_retried_task(
    tmp_path: Path,
) -> None:
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
        group_name_or_id=group.id,
        goal_text="Ship the first Pantheon slice",
    )

    bootstrap_database(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            UPDATE goals
            SET status = ?, started_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                "queued",
                None,
                "2026-04-15T00:00:00Z",
                submission.goal.id,
            ),
        )
        connection.execute(
            """
            UPDATE tasks
            SET status = ?, result_text = ?, started_at = ?, completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                "queued",
                None,
                "2026-04-15T00:00:00Z",
                None,
                "2026-04-15T00:00:01Z",
                submission.root_task.id,
            ),
        )
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
                "run-1",
                submission.root_task.id,
                lead.id,
                1,
                "failed",
                None,
                None,
                1,
                "prior failure",
                str(tmp_path / "logs" / "run-1.log"),
                None,
                "2026-04-15T00:00:00Z",
                "2026-04-15T00:00:01Z",
                "2026-04-15T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    start_result = start_goal_execution(db_path, submission.goal.id)

    assert [run.attempt_number for run in start_result.runs] == [2]

    status = get_goal_status(db_path, submission.goal.id)
    assert [run.attempt_number for run in status.runs] == [1, 2]


def test_start_goal_execution_rejects_missing_goal(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    with pytest.raises(ValueError, match="goal not found"):
        start_goal_execution(db_path, "missing-goal")


def test_start_goal_execution_requires_queued_goal_state(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    group = create_group(db_path, "research")
    create_agent(
        db_path,
        group_name_or_id=group.id,
        name="lead-1",
        role="lead",
        hermes_home="/tmp/hermes-home",
        workdir="/tmp/workdir",
    )
    submission = submit_goal(
        db_path,
        group_name_or_id=group.id,
        goal_text="Ship the first Pantheon slice",
    )

    start_goal_execution(db_path, submission.goal.id)

    with pytest.raises(ValueError, match="goal is not startable from state running"):
        start_goal_execution(db_path, submission.goal.id)


def test_start_goal_execution_with_busy_agent_does_not_false_start(tmp_path: Path) -> None:
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
        group_name_or_id=group.id,
        goal_text="Ship the first Pantheon slice",
    )

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            UPDATE agents
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            ("busy", "2026-04-15T00:00:00Z", lead.id),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ValueError, match=f"assigned agent is not idle: {lead.id}"):
        start_goal_execution(db_path, submission.goal.id)

    connection = sqlite3.connect(db_path)
    try:
        goal_row = connection.execute(
            """
            SELECT status, started_at
            FROM goals
            WHERE id = ?
            """,
            (submission.goal.id,),
        ).fetchone()
        run_count = connection.execute("SELECT COUNT(*) FROM runs").fetchone()
    finally:
        connection.close()

    assert goal_row == ("queued", None)
    assert run_count == (0,)
    assert get_events_for_goal(db_path, submission.goal.id) == []


def test_start_goal_execution_converts_adapter_exception_to_terminal_failure(
    tmp_path: Path,
) -> None:
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
        group_name_or_id=group.id,
        goal_text="Ship the first Pantheon slice",
    )

    start_result = start_goal_execution(
        db_path, submission.goal.id, adapter=RaisingAdapter()
    )

    assert len(start_result.runs) == 1
    run = start_result.runs[0]
    assert run.status == "failed"
    assert run.error_text == "adapter exploded"
    assert run.finished_at is not None

    connection = sqlite3.connect(db_path)
    try:
        goal_row = connection.execute(
            """
            SELECT status, started_at, completed_at
            FROM goals
            WHERE id = ?
            """,
            (submission.goal.id,),
        ).fetchone()
        task_row = connection.execute(
            """
            SELECT status, result_text, completed_at
            FROM tasks
            WHERE id = ?
            """,
            (submission.root_task.id,),
        ).fetchone()
        agent_row = connection.execute(
            """
            SELECT status
            FROM agents
            WHERE id = ?
            """,
            (lead.id,),
        ).fetchone()
        run_row = connection.execute(
            """
            SELECT status, error_text, finished_at
            FROM runs
            WHERE id = ?
            """,
            (run.id,),
        ).fetchone()
    finally:
        connection.close()

    assert goal_row == ("running", start_result.started_at, None)
    assert task_row == ("failed", "", run.finished_at)
    assert agent_row == ("idle",)
    assert run_row == ("failed", "adapter exploded", run.finished_at)

    assert [event.event_type for event in get_events_for_goal(db_path, submission.goal.id)] == [
        "goal.started",
        "run.started",
        "task.started",
        "run.failed",
        "task.failed",
    ]


def test_start_goal_execution_keeps_goal_running_when_all_tasks_terminal_without_completion_judgment(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "pantheon.db"

    group = create_group(db_path, "research")
    create_agent(
        db_path,
        group_name_or_id=group.id,
        name="lead-1",
        role="lead",
        hermes_home="/tmp/hermes-home",
        workdir="/tmp/workdir",
    )
    submission = submit_goal(
        db_path,
        group_name_or_id=group.id,
        goal_text="Ship the first Pantheon slice",
    )

    start_goal_execution(db_path, submission.goal.id, adapter=RaisingAdapter())

    connection = sqlite3.connect(db_path)
    try:
        goal_row = connection.execute(
            """
            SELECT status, completed_at
            FROM goals
            WHERE id = ?
            """,
            (submission.goal.id,),
        ).fetchone()
    finally:
        connection.close()

    assert goal_row == ("running", None)


def test_start_goal_execution_only_dispatches_tasks_with_complete_parent(
    tmp_path: Path,
) -> None:
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
        group_name_or_id=group.id,
        goal_text="Ship the first Pantheon slice",
    )

    connection = sqlite3.connect(db_path)
    try:
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
                "task-child-1",
                submission.goal.id,
                submission.root_task.id,
                lead.id,
                "Review outputs",
                "Review outputs",
                None,
                "queued",
                5,
                1,
                "2026-04-15T00:00:01Z",
                None,
                None,
                "2026-04-15T00:00:01Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    start_result = start_goal_execution(db_path, submission.goal.id)

    assert [run.task_id for run in start_result.runs] == [
        submission.root_task.id,
        "task-child-1",
    ]

    connection = sqlite3.connect(db_path)
    try:
        child_row = connection.execute(
            """
            SELECT status, started_at, completed_at
            FROM tasks
            WHERE id = ?
            """,
            ("task-child-1",),
        ).fetchone()
        goal_row = connection.execute(
            """
            SELECT status, completed_at
            FROM goals
            WHERE id = ?
            """,
            (submission.goal.id,),
        ).fetchone()
        run_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM runs
            """
        ).fetchone()
    finally:
        connection.close()

    assert child_row[0] == "complete"
    assert child_row[1] is not None
    assert child_row[2] is not None
    assert goal_row == ("running", None)
    assert run_count == (2,)


def test_start_goal_execution_picks_up_newly_ready_child_in_same_pass(
    tmp_path: Path,
) -> None:
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
        group_name_or_id=group.id,
        goal_text="Ship the first Pantheon slice",
    )

    connection = sqlite3.connect(db_path)
    try:
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
                "task-child-1",
                submission.goal.id,
                submission.root_task.id,
                lead.id,
                "Review outputs",
                "Review outputs",
                None,
                "queued",
                5,
                1,
                "2026-04-15T00:00:01Z",
                None,
                None,
                "2026-04-15T00:00:01Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    start_result = start_goal_execution(db_path, submission.goal.id)

    assert [run.task_id for run in start_result.runs] == [
        submission.root_task.id,
        "task-child-1",
    ]

    connection = sqlite3.connect(db_path)
    try:
        task_rows = connection.execute(
            """
            SELECT id, status
            FROM tasks
            WHERE goal_id = ?
            ORDER BY depth ASC, created_at ASC, id ASC
            """,
            (submission.goal.id,),
        ).fetchall()
        run_rows = connection.execute(
            """
            SELECT task_id, attempt_number, runs.status
            FROM runs
            JOIN tasks ON tasks.id = runs.task_id
            WHERE tasks.goal_id = ?
            ORDER BY runs.rowid ASC
            """,
            (submission.goal.id,),
        ).fetchall()
    finally:
        connection.close()

    assert task_rows == [
        (submission.root_task.id, "complete"),
        ("task-child-1", "complete"),
    ]
    assert run_rows == [
        (submission.root_task.id, 1, "complete"),
        ("task-child-1", 1, "complete"),
    ]


def test_start_goal_execution_skips_ineligible_task_and_dispatches_later_eligible_task(
    tmp_path: Path,
) -> None:
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
    worker = create_agent(
        db_path,
        group_name_or_id=group.id,
        name="worker-1",
        role="worker",
        hermes_home="/tmp/hermes-home-worker",
        workdir="/tmp/workdir-worker",
    )
    submission = submit_goal(
        db_path,
        group_name_or_id=group.id,
        goal_text="Ship the first Pantheon slice",
    )

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            UPDATE agents
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            ("busy", "2026-04-15T00:00:00Z", lead.id),
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
                "task-worker-1",
                submission.goal.id,
                None,
                worker.id,
                "Worker follow-up",
                "Worker follow-up",
                None,
                "queued",
                5,
                0,
                "2026-04-15T00:00:01Z",
                None,
                None,
                "2026-04-15T00:00:01Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    start_result = start_goal_execution(db_path, submission.goal.id)

    assert [run.task_id for run in start_result.runs] == ["task-worker-1"]

    connection = sqlite3.connect(db_path)
    try:
        root_row = connection.execute(
            """
            SELECT status, started_at, completed_at
            FROM tasks
            WHERE id = ?
            """,
            (submission.root_task.id,),
        ).fetchone()
        worker_row = connection.execute(
            """
            SELECT status, started_at, completed_at
            FROM tasks
            WHERE id = ?
            """,
            ("task-worker-1",),
        ).fetchone()
        run_rows = connection.execute(
            """
            SELECT task_id, status
            FROM runs
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()
    finally:
        connection.close()

    assert root_row == ("queued", None, None)
    assert worker_row[0] == "complete"
    assert worker_row[1] is not None
    assert worker_row[2] is not None
    assert run_rows == [("task-worker-1", "complete")]
