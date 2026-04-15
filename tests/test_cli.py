import sqlite3
import subprocess
from pathlib import Path

from pantheon.db import bootstrap_database


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
