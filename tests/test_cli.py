import sqlite3
import subprocess
from pathlib import Path

from pantheon.db import bootstrap_database, create_agent, create_group, submit_goal


def run_pantheon(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "uv",
            "run",
            "pantheon",
            "--db",
            str(db_path),
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_group_init_creates_group(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    result = run_pantheon(db_path, "group", "init", "research")

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.startswith("created group ")
    assert result.stdout.endswith(" research\n")

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute("SELECT id, name FROM groups").fetchone()
    finally:
        connection.close()

    assert row is not None
    assert row[1] == "research"
    assert result.stdout == f"created group {row[0]} research\n"


def test_group_list_prints_header_for_empty_database(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    result = run_pantheon(db_path, "group", "list")

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == "id\tname\tcreated_at\tupdated_at\n"


def test_group_list_prints_groups_in_stable_order(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    bootstrap_database(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.executemany(
            """
            INSERT INTO groups (id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("group-b", "beta", "2026-04-15T00:00:00Z", "2026-04-15T00:00:00Z"),
                ("group-a", "alpha", "2026-04-15T00:00:00Z", "2026-04-15T00:00:00Z"),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    result = run_pantheon(db_path, "group", "list")

    assert result.returncode == 0
    assert result.stderr == ""

    lines = result.stdout.splitlines()
    assert lines[0] == "id\tname\tcreated_at\tupdated_at"
    assert len(lines) == 3

    alpha_columns = lines[1].split("\t")
    beta_columns = lines[2].split("\t")

    assert alpha_columns[0] == "group-a"
    assert alpha_columns[1] == "alpha"
    assert alpha_columns[2] == "2026-04-15T00:00:00Z"
    assert alpha_columns[3] == "2026-04-15T00:00:00Z"
    assert beta_columns[0] == "group-b"
    assert beta_columns[1] == "beta"
    assert beta_columns[2] == "2026-04-15T00:00:00Z"
    assert beta_columns[3] == "2026-04-15T00:00:00Z"
    assert len(alpha_columns) == 4
    assert len(beta_columns) == 4


def test_agent_add_creates_agent(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    group_result = run_pantheon(db_path, "group", "init", "research")
    assert group_result.returncode == 0

    result = run_pantheon(
        db_path,
        "agent",
        "add",
        "--group",
        "research",
        "--name",
        "lead-1",
        "--role",
        "lead",
        "--hermes-home",
        "/tmp/hermes-home",
        "--workdir",
        "/tmp/workdir",
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.startswith("created agent ")
    assert result.stdout.endswith(" lead-1\n")

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT name, role, hermes_home, workdir, status
            FROM agents
            """
        ).fetchone()
    finally:
        connection.close()

    assert row == ("lead-1", "lead", "/tmp/hermes-home", "/tmp/workdir", "idle")


def test_agent_add_rejects_second_lead_in_group(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    group_result = run_pantheon(db_path, "group", "init", "research")
    assert group_result.returncode == 0

    first_lead = run_pantheon(
        db_path,
        "agent",
        "add",
        "--group",
        "research",
        "--name",
        "lead-1",
        "--role",
        "lead",
        "--hermes-home",
        "/tmp/hermes-home-1",
        "--workdir",
        "/tmp/workdir-1",
    )
    assert first_lead.returncode == 0

    second_lead = run_pantheon(
        db_path,
        "agent",
        "add",
        "--group",
        "research",
        "--name",
        "lead-2",
        "--role",
        "lead",
        "--hermes-home",
        "/tmp/hermes-home-2",
        "--workdir",
        "/tmp/workdir-2",
    )

    assert second_lead.returncode == 1
    assert second_lead.stdout == ""
    assert second_lead.stderr == "group already has a lead agent\n"

    connection = sqlite3.connect(db_path)
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM agents WHERE group_id = (SELECT id FROM groups WHERE name = ?)",
            ("research",),
        ).fetchone()
    finally:
        connection.close()

    assert count == (1,)


def test_goal_submit_creates_goal_and_root_task(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    group_result = run_pantheon(db_path, "group", "init", "research")
    assert group_result.returncode == 0

    lead_result = run_pantheon(
        db_path,
        "agent",
        "add",
        "--group",
        "research",
        "--name",
        "lead-1",
        "--role",
        "lead",
        "--hermes-home",
        "/tmp/hermes-home",
        "--workdir",
        "/tmp/workdir",
    )
    assert lead_result.returncode == 0

    result = run_pantheon(
        db_path,
        "goal",
        "submit",
        "Ship the first Pantheon slice",
        "--group",
        "research",
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.startswith("created goal ")
    assert " root_task " in result.stdout

    columns = result.stdout.strip().split()
    assert len(columns) == 5
    assert columns[0] == "created"
    assert columns[1] == "goal"
    assert columns[3] == "root_task"

    goal_id = columns[2]
    root_task_id = columns[4]

    connection = sqlite3.connect(db_path)
    try:
        goal_row = connection.execute(
            """
            SELECT id, title, status, root_task_id
            FROM goals
            """
        ).fetchone()
        task_row = connection.execute(
            """
            SELECT tasks.id, tasks.goal_id, tasks.assigned_agent_id, tasks.title, tasks.input_text, tasks.status, tasks.depth, agents.role
            FROM tasks
            JOIN agents ON agents.id = tasks.assigned_agent_id
            """
        ).fetchone()
    finally:
        connection.close()

    assert goal_row == (
        goal_id,
        "Ship the first Pantheon slice",
        "queued",
        root_task_id,
    )
    assert task_row is not None
    assert task_row[0] == root_task_id
    assert task_row[2] is not None
    assert task_row[3] == "Ship the first Pantheon slice"
    assert task_row[4] == "Ship the first Pantheon slice"
    assert task_row[5] == "queued"
    assert task_row[6] == 0
    assert task_row[7] == "lead"


def test_goal_submit_fails_when_group_is_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    result = run_pantheon(
        db_path,
        "goal",
        "submit",
        "Ship the first Pantheon slice",
        "--group",
        "missing",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "group not found\n"


def test_goal_submit_fails_when_group_has_no_lead(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    group_result = run_pantheon(db_path, "group", "init", "research")
    assert group_result.returncode == 0

    worker_result = run_pantheon(
        db_path,
        "agent",
        "add",
        "--group",
        "research",
        "--name",
        "worker-1",
        "--role",
        "worker",
        "--hermes-home",
        "/tmp/hermes-home",
        "--workdir",
        "/tmp/workdir",
    )
    assert worker_result.returncode == 0

    result = run_pantheon(
        db_path,
        "goal",
        "submit",
        "Ship the first Pantheon slice",
        "--group",
        "research",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "group has no lead agent\n"


def test_status_prints_goal_summary_and_task_rows(tmp_path: Path) -> None:
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

    result = run_pantheon(db_path, "status", submission.goal.id)

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.splitlines() == [
        f"goal\t{submission.goal.id}\tShip the first Pantheon slice\tqueued\t{submission.root_task.id}",
        f"task\t{submission.root_task.id}\t{lead.id}\tShip the first Pantheon slice\tqueued\t0",
        f"task\ttask-child-1\t{lead.id}\tReview outputs\trunning\t1",
    ]


def test_status_fails_when_goal_is_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    result = run_pantheon(db_path, "status", "missing-goal")

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "goal not found\n"


def test_status_prints_tasks_in_stable_order(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    bootstrap_database(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO groups (id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            ("group-1", "research", "2026-04-15T00:00:00Z", "2026-04-15T00:00:00Z"),
        )
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
                "agent-1",
                "group-1",
                "lead-1",
                "lead",
                None,
                "/tmp/hermes-home",
                "/tmp/workdir",
                None,
                None,
                "idle",
                "2026-04-15T00:00:00Z",
                "2026-04-15T00:00:00Z",
            ),
        )
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
            (
                "goal-1",
                "group-1",
                "Ship the first Pantheon slice",
                "running",
                "task-root",
                None,
                None,
                "2026-04-15T00:00:00Z",
                "2026-04-15T00:00:00Z",
            ),
        )
        connection.executemany(
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
            [
                (
                    "task-depth-1-late",
                    "goal-1",
                    "task-root",
                    "agent-1",
                    "Late child",
                    "Late child",
                    None,
                    "queued",
                    5,
                    1,
                    "2026-04-15T00:00:03Z",
                    None,
                    None,
                    "2026-04-15T00:00:03Z",
                ),
                (
                    "task-root",
                    "goal-1",
                    None,
                    "agent-1",
                    "Root task",
                    "Root task",
                    None,
                    "complete",
                    5,
                    0,
                    "2026-04-15T00:00:00Z",
                    None,
                    None,
                    "2026-04-15T00:00:00Z",
                ),
                (
                    "task-depth-1-early",
                    "goal-1",
                    "task-root",
                    "agent-1",
                    "Early child",
                    "Early child",
                    None,
                    "running",
                    5,
                    1,
                    "2026-04-15T00:00:01Z",
                    None,
                    None,
                    "2026-04-15T00:00:01Z",
                ),
                (
                    "task-depth-1-tie-a",
                    "goal-1",
                    "task-root",
                    "agent-1",
                    "Tie A",
                    "Tie A",
                    None,
                    "queued",
                    5,
                    1,
                    "2026-04-15T00:00:02Z",
                    None,
                    None,
                    "2026-04-15T00:00:02Z",
                ),
                (
                    "task-depth-1-tie-b",
                    "goal-1",
                    "task-root",
                    "agent-1",
                    "Tie B",
                    "Tie B",
                    None,
                    "queued",
                    5,
                    1,
                    "2026-04-15T00:00:02Z",
                    None,
                    None,
                    "2026-04-15T00:00:02Z",
                ),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    result = run_pantheon(db_path, "status", "goal-1")

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.splitlines() == [
        "goal\tgoal-1\tShip the first Pantheon slice\trunning\ttask-root",
        "task\ttask-root\tagent-1\tRoot task\tcomplete\t0",
        "task\ttask-depth-1-early\tagent-1\tEarly child\trunning\t1",
        "task\ttask-depth-1-tie-a\tagent-1\tTie A\tqueued\t1",
        "task\ttask-depth-1-tie-b\tagent-1\tTie B\tqueued\t1",
        "task\ttask-depth-1-late\tagent-1\tLate child\tqueued\t1",
    ]


def test_start_executes_queued_goal_and_status_prints_runs(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    group_result = run_pantheon(db_path, "group", "init", "research")
    assert group_result.returncode == 0

    agent_result = run_pantheon(
        db_path,
        "agent",
        "add",
        "--group",
        "research",
        "--name",
        "lead-1",
        "--role",
        "lead",
        "--hermes-home",
        "/tmp/hermes-home",
        "--workdir",
        "/tmp/workdir",
    )
    assert agent_result.returncode == 0

    goal_result = run_pantheon(
        db_path,
        "goal",
        "submit",
        "Ship the first Pantheon slice",
        "--group",
        "research",
    )
    assert goal_result.returncode == 0
    goal_id = goal_result.stdout.strip().split()[2]

    start_result = run_pantheon(db_path, "start", goal_id)

    assert start_result.returncode == 0
    assert start_result.stderr == ""
    assert start_result.stdout.startswith(f"started goal {goal_id} runs 1\n")

    status_result = run_pantheon(db_path, "status", goal_id)

    assert status_result.returncode == 0
    assert status_result.stderr == ""
    lines = status_result.stdout.splitlines()
    assert lines[0].startswith(f"goal\t{goal_id}\tShip the first Pantheon slice\trunning\t")
    assert lines[1].endswith("\tcomplete\t0")
    assert lines[2].startswith("run\t")
    run_columns = lines[2].split("\t")
    assert run_columns[2] == "1"
    assert run_columns[3] == "complete"
    assert run_columns[4] == lines[1].split("\t")[1]


def test_start_fails_when_goal_is_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    result = run_pantheon(db_path, "start", "missing-goal")

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "goal not found\n"


def test_start_fails_when_goal_is_not_startable(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    group_result = run_pantheon(db_path, "group", "init", "research")
    assert group_result.returncode == 0

    agent_result = run_pantheon(
        db_path,
        "agent",
        "add",
        "--group",
        "research",
        "--name",
        "lead-1",
        "--role",
        "lead",
        "--hermes-home",
        "/tmp/hermes-home",
        "--workdir",
        "/tmp/workdir",
    )
    assert agent_result.returncode == 0

    goal_result = run_pantheon(
        db_path,
        "goal",
        "submit",
        "Ship the first Pantheon slice",
        "--group",
        "research",
    )
    assert goal_result.returncode == 0
    goal_id = goal_result.stdout.strip().split()[2]

    first_start = run_pantheon(db_path, "start", goal_id)
    assert first_start.returncode == 0

    second_start = run_pantheon(db_path, "start", goal_id)

    assert second_start.returncode == 1
    assert second_start.stdout == ""
    assert second_start.stderr == "goal is not startable from state running\n"
