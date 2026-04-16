import asyncio
import sqlite3
from pathlib import Path

from textual.widgets import ListView, Static

from pantheon.db import bootstrap_database, create_agent, create_group, submit_goal
from pantheon.tui import PantheonApp
from pantheon.tui.screens.agents import AgentsScreen
from pantheon.tui.screens.group_selector import GroupSelectorScreen
from pantheon.tui.screens.goals import GoalsScreen
from pantheon.tui.screens.inspection import (
    GoalEventHistoryScreen,
    GoalInspectionScreen,
    RunEventHistoryScreen,
    RunInspectionScreen,
    TaskEventHistoryScreen,
    TaskInspectionScreen,
)
from pantheon.tui.screens.runs import RunsScreen
from pantheon.tui.screens.tasks import TasksScreen


SCREEN_BINDINGS = (
    (
        "1",
        "overview",
        (
            "overview-primary-readout",
            "overview-live-feed",
            "overview-agents",
            "overview-group-topology",
            "overview-recent-activity",
        ),
    ),
    ("2", "agents", ("agents-list", "agents-detail")),
    ("3", "goals", ("goals-list", "goals-detail")),
    ("4", "tasks", ("tasks-list", "tasks-detail")),
    ("5", "runs", ("runs-list", "runs-detail")),
    (
        "6",
        "settings",
        (
            "settings-app-info",
            "settings-database-path",
            "settings-runtime-notes",
            "settings-future-placeholder",
        ),
    ),
)


def _write_run_log(logs_dir: Path, name: str, content: str) -> str:
    path = logs_dir / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def _seed_readonly_tui_data(db_path: Path) -> dict[str, str]:
    bootstrap_database(db_path)
    logs_dir = db_path.parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    group = create_group(db_path, "alpha")
    lead = create_agent(
        db_path,
        group_name_or_id=group.id,
        name="lead-1",
        role="lead",
        hermes_home="/tmp/hermes-home-lead",
        workdir="/tmp/workdir-lead",
    )
    worker = create_agent(
        db_path,
        group_name_or_id=group.id,
        name="worker-1",
        role="worker",
        hermes_home="/tmp/hermes-home-worker",
        workdir="/tmp/workdir-worker",
    )
    goal_one = submit_goal(
        db_path,
        group_name_or_id=group.id,
        goal_text="Ship slice A",
    )
    goal_two = submit_goal(
        db_path,
        group_name_or_id=group.id,
        goal_text="Ship slice B",
    )

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            UPDATE groups
            SET created_at = ?, updated_at = ?
            WHERE id = ?
            """,
            ("2026-04-15T00:00:00Z", "2026-04-15T00:00:00Z", group.id),
        )
        connection.execute(
            """
            UPDATE goals
            SET created_at = ?, updated_at = ?
            WHERE id = ?
            """,
            ("2026-04-15T00:00:01Z", "2026-04-15T00:00:03Z", goal_one.goal.id),
        )
        connection.execute(
            """
            UPDATE goals
            SET created_at = ?, updated_at = ?
            WHERE id = ?
            """,
            ("2026-04-15T00:00:02Z", "2026-04-15T00:00:04Z", goal_two.goal.id),
        )
        connection.execute(
            """
            UPDATE agents
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            ("busy", "2026-04-15T00:00:03Z", worker.id),
        )
        connection.execute(
            """
            UPDATE goals
            SET status = ?, started_at = ?, updated_at = ?
            WHERE id = ?
            """,
            ("running", "2026-04-15T00:00:01Z", "2026-04-15T00:00:03Z", goal_one.goal.id),
        )
        connection.execute(
            """
            UPDATE goals
            SET status = ?, started_at = ?, updated_at = ?
            WHERE id = ?
            """,
            ("running", "2026-04-15T00:00:02Z", "2026-04-15T00:00:04Z", goal_two.goal.id),
        )
        connection.execute(
            """
            UPDATE tasks
            SET status = ?, result_text = ?, created_at = ?, started_at = ?, completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                "complete",
                "Lead summary ready",
                "2026-04-15T00:00:01Z",
                "2026-04-15T00:00:01Z",
                "2026-04-15T00:00:03Z",
                "2026-04-15T00:00:03Z",
                goal_one.root_task.id,
            ),
        )
        connection.execute(
            """
            UPDATE tasks
            SET status = ?, result_text = ?, created_at = ?, started_at = ?, completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                "failed",
                "Blocked on dependency",
                "2026-04-15T00:00:02Z",
                "2026-04-15T00:00:02Z",
                "2026-04-15T00:00:04Z",
                "2026-04-15T00:00:04Z",
                goal_two.root_task.id,
            ),
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
                "task-child-1",
                goal_one.goal.id,
                goal_one.root_task.id,
                worker.id,
                "Review output",
                "Review output",
                None,
                "running",
                5,
                1,
                "2026-04-15T00:00:03Z",
                "2026-04-15T00:00:03Z",
                None,
                "2026-04-15T00:00:03Z",
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
                goal_one.root_task.id,
                lead.id,
                1,
                "complete",
                "sess-1",
                None,
                0,
                None,
                _write_run_log(
                    logs_dir,
                    "run-1.log",
                    "run-1 line 1\nrun-1 line 2\nrun-1 line 3\n",
                ),
                None,
                "2026-04-15T00:00:01Z",
                "2026-04-15T00:00:03Z",
                "2026-04-15T00:00:01Z",
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
                "run-2",
                goal_two.root_task.id,
                lead.id,
                1,
                "failed",
                "sess-2",
                None,
                1,
                "adapter failed",
                _write_run_log(
                    logs_dir,
                    "run-2.log",
                    "run-2 error line 1\nrun-2 error line 2\n",
                ),
                None,
                "2026-04-15T00:00:02Z",
                "2026-04-15T00:00:04Z",
                "2026-04-15T00:00:02Z",
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
                "run-3",
                "task-child-1",
                worker.id,
                1,
                "running",
                "sess-3",
                None,
                None,
                None,
                _write_run_log(
                    logs_dir,
                    "run-3.log",
                    "run-3 active line 1\nrun-3 active line 2\n",
                ),
                None,
                "2026-04-15T00:00:03Z",
                None,
                "2026-04-15T00:00:03Z",
            ),
        )
        connection.executemany(
            """
            INSERT INTO events (
                id,
                goal_id,
                task_id,
                run_id,
                agent_id,
                event_type,
                payload_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "event-1",
                    goal_one.goal.id,
                    goal_one.root_task.id,
                    "run-1",
                    lead.id,
                    "run.completed",
                    '{"status":"complete","attempt_number":1}',
                    "2026-04-15T00:00:05Z",
                ),
                (
                    "event-2",
                    goal_two.goal.id,
                    goal_two.root_task.id,
                    "run-2",
                    lead.id,
                    "run.failed",
                    '{"status":"failed","error":"adapter failed"}',
                    "2026-04-15T00:00:06Z",
                ),
                (
                    "event-3",
                    goal_one.goal.id,
                    "task-child-1",
                    None,
                    worker.id,
                    "task.started",
                    '{"status":"running","assigned_agent":"worker-1"}',
                    "2026-04-15T00:00:07Z",
                ),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    return {
        "group_id": group.id,
        "lead_id": lead.id,
        "worker_id": worker.id,
        "goal_one_id": goal_one.goal.id,
        "goal_two_id": goal_two.goal.id,
        "task_one_id": goal_one.root_task.id,
        "task_two_id": goal_two.root_task.id,
        "task_child_id": "task-child-1",
        "run_one_id": "run-1",
        "run_two_id": "run-2",
        "run_three_id": "run-3",
    }


def _seed_secondary_group_data(db_path: Path) -> dict[str, str]:
    bootstrap_database(db_path)
    group = create_group(db_path, "beta")
    lead = create_agent(
        db_path,
        group_name_or_id=group.id,
        name="lead-2",
        role="lead",
        hermes_home="/tmp/hermes-home-lead-2",
        workdir="/tmp/workdir-lead-2",
    )
    goal = submit_goal(
        db_path,
        group_name_or_id=group.id,
        goal_text="Ship slice C",
    )

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            UPDATE groups
            SET created_at = ?, updated_at = ?
            WHERE id = ?
            """,
            ("2026-04-15T00:00:10Z", "2026-04-15T00:00:10Z", group.id),
        )
        connection.execute(
            """
            UPDATE goals
            SET created_at = ?, updated_at = ?
            WHERE id = ?
            """,
            ("2026-04-15T00:00:11Z", "2026-04-15T00:00:11Z", goal.goal.id),
        )
        connection.execute(
            """
            UPDATE tasks
            SET created_at = ?, updated_at = ?
            WHERE id = ?
            """,
            ("2026-04-15T00:00:11Z", "2026-04-15T00:00:11Z", goal.root_task.id),
        )
        connection.commit()
    finally:
        connection.close()

    return {
        "group_id": group.id,
        "lead_id": lead.id,
        "goal_id": goal.goal.id,
        "task_id": goal.root_task.id,
    }


def _seed_empty_group(db_path: Path) -> dict[str, str]:
    bootstrap_database(db_path)
    group = create_group(db_path, "gamma")
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            UPDATE groups
            SET created_at = ?, updated_at = ?
            WHERE id = ?
            """,
            ("2026-04-15T00:00:20Z", "2026-04-15T00:00:20Z", group.id),
        )
        connection.commit()
    finally:
        connection.close()
    return {"group_id": group.id}


def _seed_goal_without_root_task(db_path: Path) -> dict[str, str]:
    bootstrap_database(db_path)
    group = create_group(db_path, "delta")
    create_agent(
        db_path,
        group_name_or_id=group.id,
        name="lead-4",
        role="lead",
        hermes_home="/tmp/hermes-home-lead-4",
        workdir="/tmp/workdir-lead-4",
    )
    goal = submit_goal(
        db_path,
        group_name_or_id=group.id,
        goal_text="Root task missing",
    )

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            UPDATE goals
            SET root_task_id = NULL, created_at = ?, updated_at = ?
            WHERE id = ?
            """,
            ("2026-04-15T00:00:30Z", "2026-04-15T00:00:31Z", goal.goal.id),
        )
        connection.execute(
            """
            UPDATE tasks
            SET created_at = ?, updated_at = ?
            WHERE id = ?
            """,
            ("2026-04-15T00:00:30Z", "2026-04-15T00:00:31Z", goal.root_task.id),
        )
        connection.commit()
    finally:
        connection.close()

    return {"group_id": group.id, "goal_id": goal.goal.id}


def _seed_run_log_preview_state(
    db_path: Path,
    *,
    log_content: str | None,
    log_filename: str = "preview.log",
) -> dict[str, str]:
    bootstrap_database(db_path)
    logs_dir = db_path.parent / "preview-logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    group = create_group(db_path, "preview-group")
    lead = create_agent(
        db_path,
        group_name_or_id=group.id,
        name="lead-preview",
        role="lead",
        hermes_home="/tmp/hermes-home-preview",
        workdir="/tmp/workdir-preview",
    )
    goal = submit_goal(
        db_path,
        group_name_or_id=group.id,
        goal_text="Preview goal",
    )

    log_path = logs_dir / log_filename
    if log_content is not None:
        log_path.write_text(log_content, encoding="utf-8")

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            UPDATE goals
            SET status = ?, started_at = ?, updated_at = ?
            WHERE id = ?
            """,
            ("running", "2026-04-16T00:00:01Z", "2026-04-16T00:00:01Z", goal.goal.id),
        )
        connection.execute(
            """
            UPDATE tasks
            SET status = ?, created_at = ?, started_at = ?, updated_at = ?
            WHERE id = ?
            """,
            ("running", "2026-04-16T00:00:01Z", "2026-04-16T00:00:01Z", "2026-04-16T00:00:01Z", goal.root_task.id),
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
                "run-preview",
                goal.root_task.id,
                lead.id,
                1,
                "running",
                "sess-preview",
                None,
                None,
                None,
                str(log_path),
                None,
                "2026-04-16T00:00:01Z",
                None,
                "2026-04-16T00:00:01Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    return {
        "group_id": group.id,
        "goal_id": goal.goal.id,
        "task_id": goal.root_task.id,
        "run_id": "run-preview",
        "log_path": str(log_path),
    }


def test_app_launches_into_overview_screen(tmp_path: Path) -> None:
    async def run_test() -> None:
        app = PantheonApp(tmp_path / "pantheon.db")
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.current_screen_name == "overview"
            assert app.sub_title == "Overview"
            assert app.screen.query_one("#overview-primary-readout", Static)

    asyncio.run(run_test())


def test_startup_resolves_first_group_as_current_group(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    first_group = create_group(db_path, "alpha")
    second_group = create_group(db_path, "beta")

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "UPDATE groups SET created_at = ?, updated_at = ? WHERE id = ?",
            ("2026-04-15T00:00:01Z", "2026-04-15T00:00:01Z", first_group.id),
        )
        connection.execute(
            "UPDATE groups SET created_at = ?, updated_at = ? WHERE id = ?",
            ("2026-04-15T00:00:02Z", "2026-04-15T00:00:02Z", second_group.id),
        )
        connection.commit()
    finally:
        connection.close()

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            primary = app.screen.query_one("#overview-primary-readout", Static)
            assert app.current_group_id == first_group.id
            assert "group: alpha" in str(primary.content)

    asyncio.run(run_test())


def test_empty_state_is_explicit_when_no_groups_exist(tmp_path: Path) -> None:
    async def run_test() -> None:
        app = PantheonApp(tmp_path / "pantheon.db")
        async with app.run_test() as pilot:
            await pilot.pause()
            primary = app.screen.query_one("#overview-primary-readout", Static)
            recent = app.screen.query_one("#overview-recent-activity", Static)
            assert app.current_group_id is None
            assert "No groups configured." in str(primary.content)
            assert "No recent activity available." in str(recent.content)

    asyncio.run(run_test())


def test_top_level_screen_switching_uses_bindings(tmp_path: Path) -> None:
    async def run_test() -> None:
        app = PantheonApp(tmp_path / "pantheon.db")
        async with app.run_test() as pilot:
            for key, expected_screen, panel_ids in SCREEN_BINDINGS:
                await pilot.press(key)
                await pilot.pause()
                assert app.current_screen_name == expected_screen
                for panel_id in panel_ids:
                    assert app.screen.query_one(f"#{panel_id}") is not None

    asyncio.run(run_test())


def test_agents_selection_updates_detail_panel(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_readonly_tui_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("2")
            await pilot.pause()
            assert isinstance(app.screen, AgentsScreen)
            detail = app.screen.query_one("#agents-detail", Static)
            assert app.screen.selected_agent_id == ids["lead_id"]
            assert "name: lead-1" in str(detail.content)

            await pilot.press("down")
            await pilot.pause()
            assert app.screen.selected_agent_id == ids["worker_id"]
            assert "name: worker-1" in str(detail.content)

    asyncio.run(run_test())


def test_goals_selection_updates_detail_panel(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_readonly_tui_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("3")
            await pilot.pause()
            assert isinstance(app.screen, GoalsScreen)
            detail = app.screen.query_one("#goals-detail", Static)
            assert app.screen.selected_goal_id == ids["goal_one_id"]
            assert "title: Ship slice A" in str(detail.content)

            await pilot.press("down")
            await pilot.pause()
            assert app.screen.selected_goal_id == ids["goal_two_id"]
            assert "title: Ship slice B" in str(detail.content)

    asyncio.run(run_test())


def test_tasks_selection_updates_detail_panel(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_readonly_tui_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("4")
            await pilot.pause()
            assert isinstance(app.screen, TasksScreen)
            detail = app.screen.query_one("#tasks-detail", Static)
            assert app.screen.selected_task_id == ids["task_one_id"]
            assert "title: Ship slice A" in str(detail.content)

            await pilot.press("down")
            await pilot.pause()
            assert app.screen.selected_task_id == ids["task_two_id"]
            assert "title: Ship slice B" in str(detail.content)

    asyncio.run(run_test())


def test_runs_selection_updates_detail_panel(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_readonly_tui_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("5")
            await pilot.pause()
            assert isinstance(app.screen, RunsScreen)
            detail = app.screen.query_one("#runs-detail", Static)
            assert app.screen.selected_run_id == ids["run_one_id"]
            assert "task: Ship slice A" in str(detail.content)
            assert "log_preview: full preview" in str(detail.content)
            assert "run-1 line 3" in str(detail.content)

            await pilot.press("down")
            await pilot.pause()
            assert app.screen.selected_run_id == ids["run_two_id"]
            assert "task: Ship slice B" in str(detail.content)
            assert "run-2 error line 2" in str(detail.content)

    asyncio.run(run_test())


def test_runs_detail_panel_shows_real_log_preview(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_run_log_preview_state(
        db_path,
        log_content="alpha\nbeta\ngamma\n",
    )

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("5")
            await pilot.pause()

            assert isinstance(app.screen, RunsScreen)
            detail = app.screen.query_one("#runs-detail", Static)
            assert app.screen.selected_run_id == ids["run_id"]
            assert "log_preview: full preview" in str(detail.content)
            assert "alpha\nbeta\ngamma" in str(detail.content)

    asyncio.run(run_test())


def test_runs_detail_panel_handles_missing_empty_and_clipped_logs(tmp_path: Path) -> None:
    missing_db_path = tmp_path / "missing.db"
    empty_db_path = tmp_path / "empty.db"
    clipped_db_path = tmp_path / "clipped.db"

    _seed_run_log_preview_state(missing_db_path, log_content=None, log_filename="missing.log")
    _seed_run_log_preview_state(empty_db_path, log_content="", log_filename="empty.log")
    _seed_run_log_preview_state(
        clipped_db_path,
        log_content="".join(f"line {index:03d}\n" for index in range(1, 61)),
        log_filename="clipped.log",
    )

    async def run_missing_test() -> None:
        app = PantheonApp(missing_db_path)
        async with app.run_test() as pilot:
            await pilot.press("5")
            await pilot.pause()
            detail = app.screen.query_one("#runs-detail", Static)
            assert "log_preview: missing" in str(detail.content)
            assert "file not found" in str(detail.content)

    async def run_empty_test() -> None:
        app = PantheonApp(empty_db_path)
        async with app.run_test() as pilot:
            await pilot.press("5")
            await pilot.pause()
            detail = app.screen.query_one("#runs-detail", Static)
            assert "log_preview: empty" in str(detail.content)
            assert "log file is empty" in str(detail.content)

    async def run_clipped_test() -> None:
        app = PantheonApp(clipped_db_path)
        async with app.run_test() as pilot:
            await pilot.press("5")
            await pilot.pause()
            detail = app.screen.query_one("#runs-detail", Static)
            content = str(detail.content)
            assert "log_preview: tail preview" in content
            assert "line 060" in content
            assert "line 021" in content
            assert "line 020" not in content

    asyncio.run(run_missing_test())
    asyncio.run(run_empty_test())
    asyncio.run(run_clipped_test())


def test_keyboard_group_switch_updates_current_group_context(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    alpha = _seed_readonly_tui_data(db_path)
    beta = _seed_secondary_group_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            context = app.query_one("#current-group-context", Static)
            assert app.current_group_id == alpha["group_id"]
            assert "Current Group: alpha (1/2)" in str(context.content)

            await pilot.press("]")
            await pilot.pause()
            assert app.current_group_id == beta["group_id"]
            assert "Current Group: beta (2/2)" in str(context.content)

            await pilot.press("[")
            await pilot.pause()
            assert app.current_group_id == alpha["group_id"]
            assert "Current Group: alpha (1/2)" in str(context.content)

    asyncio.run(run_test())


def test_group_selector_opens_from_shell(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    _seed_readonly_tui_data(db_path)
    _seed_secondary_group_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("5")
            await pilot.pause()
            await pilot.press("g")
            await pilot.pause()

            assert isinstance(app.screen, GroupSelectorScreen)
            selector = app.screen.query_one("#group-selector-list", ListView)
            assert selector is not None

    asyncio.run(run_test())


def test_group_selector_keyboard_navigation_tracks_highlight(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    alpha = _seed_readonly_tui_data(db_path)
    beta = _seed_secondary_group_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("g")
            await pilot.pause()

            assert isinstance(app.screen, GroupSelectorScreen)
            list_view = app.screen.query_one("#group-selector-list", ListView)
            assert list_view.index == 0
            assert alpha["group_id"] in str(list_view.children[0].query_one(Static).content)

            await pilot.press("down")
            await pilot.pause()
            assert list_view.index == 1
            assert beta["group_id"] in str(list_view.children[1].query_one(Static).content)

            await pilot.press("up")
            await pilot.pause()
            assert list_view.index == 0

    asyncio.run(run_test())


def test_group_selector_choose_specific_group_updates_context(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    _seed_readonly_tui_data(db_path)
    beta = _seed_secondary_group_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            context = app.query_one("#current-group-context", Static)

            await pilot.press("g")
            await pilot.pause()
            await pilot.press("down", "enter")
            await pilot.pause()

            assert app.current_group_id == beta["group_id"]
            assert "Current Group: beta (2/2)" in str(context.content)

    asyncio.run(run_test())


def test_active_screen_refreshes_after_group_switch(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    _seed_readonly_tui_data(db_path)
    beta = _seed_secondary_group_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("3")
            await pilot.pause()
            assert isinstance(app.screen, GoalsScreen)
            detail = app.screen.query_one("#goals-detail", Static)
            assert "title: Ship slice A" in str(detail.content)

            await pilot.press("]")
            await pilot.pause()
            assert app.current_group_id == beta["group_id"]
            assert app.screen.selected_goal_id == beta["goal_id"]
            assert "title: Ship slice C" in str(detail.content)

    asyncio.run(run_test())


def test_active_screen_refreshes_after_explicit_group_selection(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    _seed_readonly_tui_data(db_path)
    beta = _seed_secondary_group_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("3")
            await pilot.pause()
            assert isinstance(app.screen, GoalsScreen)
            detail = app.screen.query_one("#goals-detail", Static)
            assert "title: Ship slice A" in str(detail.content)

            await pilot.press("g")
            await pilot.pause()
            await pilot.press("down", "enter")
            await pilot.pause()

            assert isinstance(app.screen, GoalsScreen)
            assert app.current_group_id == beta["group_id"]
            assert app.screen.selected_goal_id == beta["goal_id"]
            assert "title: Ship slice C" in str(detail.content)

    asyncio.run(run_test())


def test_group_switch_revalidates_screen_selection(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    alpha = _seed_readonly_tui_data(db_path)
    beta = _seed_secondary_group_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("2")
            await pilot.pause()
            assert isinstance(app.screen, AgentsScreen)
            detail = app.screen.query_one("#agents-detail", Static)

            await pilot.press("down")
            await pilot.pause()
            assert app.screen.selected_agent_id == alpha["worker_id"]
            assert "name: worker-1" in str(detail.content)

            await pilot.press("]")
            await pilot.pause()
            assert app.current_group_id == beta["group_id"]
            assert app.screen.selected_agent_id == beta["lead_id"]
            assert "name: lead-2" in str(detail.content)

    asyncio.run(run_test())


def test_group_selector_cancel_keeps_current_group(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    alpha = _seed_readonly_tui_data(db_path)
    _seed_secondary_group_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            context = app.query_one("#current-group-context", Static)

            await pilot.press("g")
            await pilot.pause()
            assert isinstance(app.screen, GroupSelectorScreen)

            await pilot.press("down", "escape")
            await pilot.pause()

            assert app.current_group_id == alpha["group_id"]
            assert "Current Group: alpha (1/2)" in str(context.content)
            assert not isinstance(app.screen, GroupSelectorScreen)

    asyncio.run(run_test())


def test_group_switch_empty_state_is_explicit_for_chosen_group(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    _seed_readonly_tui_data(db_path)
    _seed_empty_group(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("4")
            await pilot.pause()
            assert isinstance(app.screen, TasksScreen)
            detail = app.screen.query_one("#tasks-detail", Static)
            assert app.screen.selected_task_id is not None

            await pilot.press("]")
            await pilot.pause()
            assert app.screen.selected_task_id is None
            assert "No tasks found in the current group." in str(detail.content)

    asyncio.run(run_test())


def test_goal_drill_in_opens_focused_inspection_and_returns_to_goals(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_readonly_tui_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("3")
            await pilot.pause()
            assert isinstance(app.screen, GoalsScreen)

            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, GoalInspectionScreen)
            body = app.screen.query_one("#inspection-body", Static)
            assert "entity_type: goal" in str(body.content)
            assert f"id: {ids['goal_one_id']}" in str(body.content)
            assert "title: Ship slice A" in str(body.content)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, GoalsScreen)
            assert app.screen.selected_goal_id == ids["goal_one_id"]

    asyncio.run(run_test())


def test_task_drill_in_opens_focused_inspection_and_returns_to_tasks(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_readonly_tui_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("4")
            await pilot.pause()
            assert isinstance(app.screen, TasksScreen)

            await pilot.press("down", "enter")
            await pilot.pause()
            assert isinstance(app.screen, TaskInspectionScreen)
            body = app.screen.query_one("#inspection-body", Static)
            assert "entity_type: task" in str(body.content)
            assert f"id: {ids['task_two_id']}" in str(body.content)
            assert "title: Ship slice B" in str(body.content)

            await pilot.press("backspace")
            await pilot.pause()
            assert isinstance(app.screen, TasksScreen)
            assert app.screen.selected_task_id == ids["task_two_id"]

    asyncio.run(run_test())


def test_run_drill_in_opens_focused_inspection_and_returns_to_runs(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_readonly_tui_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("5")
            await pilot.pause()
            assert isinstance(app.screen, RunsScreen)

            await pilot.press("down", "enter")
            await pilot.pause()
            assert isinstance(app.screen, RunInspectionScreen)
            body = app.screen.query_one("#inspection-body", Static)
            assert "entity_type: run" in str(body.content)
            assert f"id: {ids['run_two_id']}" in str(body.content)
            assert "task: Ship slice B" in str(body.content)
            assert "log_preview: full preview" in str(body.content)
            assert "run-2 error line 2" in str(body.content)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, RunsScreen)
            assert app.screen.selected_run_id == ids["run_two_id"]

    asyncio.run(run_test())


def test_run_inspection_shows_real_log_preview(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_run_log_preview_state(
        db_path,
        log_content="inspect line 1\ninspect line 2\n",
    )

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("5", "enter")
            await pilot.pause()

            assert isinstance(app.screen, RunInspectionScreen)
            body = app.screen.query_one("#inspection-body", Static)
            assert f"id: {ids['run_id']}" in str(body.content)
            assert "log_preview: full preview" in str(body.content)
            assert "inspect line 2" in str(body.content)

    asyncio.run(run_test())


def test_drill_in_preserves_current_group_context_on_return(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    _seed_readonly_tui_data(db_path)
    beta = _seed_secondary_group_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            context = app.query_one("#current-group-context", Static)

            await pilot.press("]")
            await pilot.pause()
            assert app.current_group_id == beta["group_id"]
            assert "Current Group: beta (2/2)" in str(context.content)

            await pilot.press("3", "enter")
            await pilot.pause()
            assert isinstance(app.screen, GoalInspectionScreen)
            body = app.screen.query_one("#inspection-body", Static)
            assert f"group_id: {beta['group_id']}" in str(body.content)
            assert "Current Group: beta (2/2)" in str(context.content)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, GoalsScreen)
            assert app.current_group_id == beta["group_id"]
            assert app.screen.selected_goal_id == beta["goal_id"]
            assert "Current Group: beta (2/2)" in str(context.content)

    asyncio.run(run_test())


def test_goal_inspection_hops_to_root_task(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_readonly_tui_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("3", "enter")
            await pilot.pause()

            assert isinstance(app.screen, GoalInspectionScreen)
            hint = app.screen.query_one("#inspection-hint", Static)
            assert "t inspect root task" in str(hint.content)

            await pilot.press("t")
            await pilot.pause()

            assert isinstance(app.screen, TaskInspectionScreen)
            body = app.screen.query_one("#inspection-body", Static)
            assert f"id: {ids['task_one_id']}" in str(body.content)
            assert "entity_type: task" in str(body.content)

    asyncio.run(run_test())


def test_goal_inspection_opens_event_history(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_readonly_tui_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("3", "enter")
            await pilot.pause()

            assert isinstance(app.screen, GoalInspectionScreen)
            hint = app.screen.query_one("#inspection-hint", Static)
            assert "e inspect event history" in str(hint.content)

            await pilot.press("e")
            await pilot.pause()

            assert isinstance(app.screen, GoalEventHistoryScreen)
            body = app.screen.query_one("#inspection-body", Static)
            content = str(body.content)
            assert f"goal_id: {ids['goal_one_id']}" in content
            assert "2026-04-15T00:00:05Z  run.completed" in content
            assert "2026-04-15T00:00:07Z  task.started" in content
            assert "payload: assigned_agent='worker-1', status='running'" in content

    asyncio.run(run_test())


def test_task_inspection_hops_to_parent_task(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_readonly_tui_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("4", "down", "down", "enter")
            await pilot.pause()

            assert isinstance(app.screen, TaskInspectionScreen)
            body = app.screen.query_one("#inspection-body", Static)
            assert f"id: {ids['task_child_id']}" in str(body.content)

            await pilot.press("p")
            await pilot.pause()

            assert isinstance(app.screen, TaskInspectionScreen)
            body = app.screen.query_one("#inspection-body", Static)
            assert f"id: {ids['task_one_id']}" in str(body.content)
            assert "title: Ship slice A" in str(body.content)

    asyncio.run(run_test())


def test_task_inspection_opens_task_event_history(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_readonly_tui_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("4", "down", "down", "enter")
            await pilot.pause()

            assert isinstance(app.screen, TaskInspectionScreen)
            hint = app.screen.query_one("#inspection-hint", Static)
            assert "e inspect event history" in str(hint.content)

            await pilot.press("e")
            await pilot.pause()

            assert isinstance(app.screen, TaskEventHistoryScreen)
            body = app.screen.query_one("#inspection-body", Static)
            content = str(body.content)
            assert f"task_id: {ids['task_child_id']}" in content
            assert "2026-04-15T00:00:07Z  task.started" in content
            assert "payload: assigned_agent='worker-1', status='running'" in content
            assert "run.completed" not in content

    asyncio.run(run_test())


def test_run_inspection_hops_to_task(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_readonly_tui_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("5", "down", "down", "enter")
            await pilot.pause()

            assert isinstance(app.screen, RunInspectionScreen)
            body = app.screen.query_one("#inspection-body", Static)
            assert f"id: {ids['run_three_id']}" in str(body.content)

            await pilot.press("t")
            await pilot.pause()

            assert isinstance(app.screen, TaskInspectionScreen)
            body = app.screen.query_one("#inspection-body", Static)
            assert f"id: {ids['task_child_id']}" in str(body.content)
            assert "title: Review output" in str(body.content)

    asyncio.run(run_test())


def test_run_inspection_opens_run_related_event_history(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_readonly_tui_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("5", "enter")
            await pilot.pause()

            assert isinstance(app.screen, RunInspectionScreen)
            hint = app.screen.query_one("#inspection-hint", Static)
            assert "e inspect related event history" in str(hint.content)

            await pilot.press("e")
            await pilot.pause()

            assert isinstance(app.screen, RunEventHistoryScreen)
            body = app.screen.query_one("#inspection-body", Static)
            content = str(body.content)
            assert f"run_id: {ids['run_one_id']}" in content
            assert "run.completed" in content
            assert "task.started" not in content
            assert "payload: attempt_number=1, status='complete'" in content

    asyncio.run(run_test())


def test_event_history_empty_state_is_explicit(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_readonly_tui_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("5", "down", "down", "enter")
            await pilot.pause()
            assert isinstance(app.screen, RunInspectionScreen)

            await pilot.press("e")
            await pilot.pause()

            assert isinstance(app.screen, RunEventHistoryScreen)
            body = app.screen.query_one("#inspection-body", Static)
            assert f"run_id: {ids['run_three_id']}" in str(body.content)
            assert "No event history recorded for this run." in str(body.content)

    asyncio.run(run_test())


def test_task_event_history_empty_state_is_explicit(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    _seed_readonly_tui_data(db_path)
    beta = _seed_secondary_group_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("]")
            await pilot.pause()

            await pilot.press("4", "enter")
            await pilot.pause()
            assert isinstance(app.screen, TaskInspectionScreen)

            await pilot.press("e")
            await pilot.pause()

            assert isinstance(app.screen, TaskEventHistoryScreen)
            body = app.screen.query_one("#inspection-body", Static)
            assert f"task_id: {beta['task_id']}" in str(body.content)
            assert "No event history recorded for this task." in str(body.content)

    asyncio.run(run_test())


def test_event_history_preserves_current_group_context(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    _seed_readonly_tui_data(db_path)
    beta = _seed_secondary_group_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            context = app.query_one("#current-group-context", Static)

            await pilot.press("]")
            await pilot.pause()
            assert app.current_group_id == beta["group_id"]
            assert "Current Group: beta (2/2)" in str(context.content)

            await pilot.press("3", "enter", "e")
            await pilot.pause()

            assert isinstance(app.screen, GoalEventHistoryScreen)
            assert "Current Group: beta (2/2)" in str(context.content)
            assert f"goal_id: {beta['goal_id']}" in str(app.screen.query_one("#inspection-body", Static).content)

    asyncio.run(run_test())


def test_task_event_history_preserves_current_group_context(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    _seed_readonly_tui_data(db_path)
    beta = _seed_secondary_group_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            context = app.query_one("#current-group-context", Static)

            await pilot.press("]")
            await pilot.pause()
            assert app.current_group_id == beta["group_id"]
            assert "Current Group: beta (2/2)" in str(context.content)

            await pilot.press("4", "enter", "e")
            await pilot.pause()

            assert isinstance(app.screen, TaskEventHistoryScreen)
            assert "Current Group: beta (2/2)" in str(context.content)
            assert f"task_id: {beta['task_id']}" in str(app.screen.query_one("#inspection-body", Static).content)

    asyncio.run(run_test())


def test_event_history_return_navigation_is_deterministic(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_readonly_tui_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("3", "enter", "e")
            await pilot.pause()

            assert isinstance(app.screen, GoalEventHistoryScreen)
            assert f"goal_id: {ids['goal_one_id']}" in str(app.screen.query_one("#inspection-body", Static).content)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, GoalInspectionScreen)
            assert f"id: {ids['goal_one_id']}" in str(app.screen.query_one("#inspection-body", Static).content)

            await pilot.press("backspace")
            await pilot.pause()
            assert isinstance(app.screen, GoalsScreen)
            assert app.screen.selected_goal_id == ids["goal_one_id"]

    asyncio.run(run_test())


def test_task_event_history_return_navigation_is_deterministic(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_readonly_tui_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("4", "down", "down", "enter", "e")
            await pilot.pause()

            assert isinstance(app.screen, TaskEventHistoryScreen)
            assert f"task_id: {ids['task_child_id']}" in str(app.screen.query_one("#inspection-body", Static).content)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, TaskInspectionScreen)
            assert f"id: {ids['task_child_id']}" in str(app.screen.query_one("#inspection-body", Static).content)

            await pilot.press("backspace")
            await pilot.pause()
            assert isinstance(app.screen, TasksScreen)
            assert app.screen.selected_task_id == ids["task_child_id"]

    asyncio.run(run_test())


def test_linked_multi_hop_return_navigation_is_predictable(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    _seed_readonly_tui_data(db_path)
    beta = _seed_secondary_group_data(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            context = app.query_one("#current-group-context", Static)

            await pilot.press("]")
            await pilot.pause()
            assert "Current Group: beta (2/2)" in str(context.content)

            await pilot.press("3", "enter")
            await pilot.pause()
            assert isinstance(app.screen, GoalInspectionScreen)
            assert f"id: {beta['goal_id']}" in str(app.screen.query_one("#inspection-body", Static).content)

            await pilot.press("t")
            await pilot.pause()
            assert isinstance(app.screen, TaskInspectionScreen)
            assert f"id: {beta['task_id']}" in str(app.screen.query_one("#inspection-body", Static).content)
            assert "Current Group: beta (2/2)" in str(context.content)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, GoalInspectionScreen)
            assert f"id: {beta['goal_id']}" in str(app.screen.query_one("#inspection-body", Static).content)

            await pilot.press("backspace")
            await pilot.pause()
            assert isinstance(app.screen, GoalsScreen)
            assert app.screen.selected_goal_id == beta["goal_id"]
            assert "Current Group: beta (2/2)" in str(context.content)

    asyncio.run(run_test())


def test_unavailable_link_is_explicit_and_safe(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"
    ids = _seed_goal_without_root_task(db_path)

    async def run_test() -> None:
        app = PantheonApp(db_path)
        async with app.run_test() as pilot:
            await pilot.press("3", "enter")
            await pilot.pause()

            assert isinstance(app.screen, GoalInspectionScreen)
            body = app.screen.query_one("#inspection-body", Static)
            hint = app.screen.query_one("#inspection-hint", Static)
            assert f"id: {ids['goal_id']}" in str(body.content)
            assert "link_root_task: t -> root task unavailable" in str(body.content)
            assert "t root task unavailable" in str(hint.content)

            await pilot.press("t")
            await pilot.pause()

            assert isinstance(app.screen, GoalInspectionScreen)
            assert f"id: {ids['goal_id']}" in str(app.screen.query_one("#inspection-body", Static).content)

    asyncio.run(run_test())
