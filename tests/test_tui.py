import asyncio
import sqlite3
from pathlib import Path

from textual.widgets import ListView, Static

from pantheon.db import bootstrap_database, create_agent, create_group, submit_goal
from pantheon.tui import PantheonApp
from pantheon.tui.screens.agents import AgentsScreen
from pantheon.tui.screens.group_selector import GroupSelectorScreen
from pantheon.tui.screens.goals import GoalsScreen
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


def _seed_readonly_tui_data(db_path: Path) -> dict[str, str]:
    bootstrap_database(db_path)
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
                "/tmp/run-1.log",
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
                "/tmp/run-2.log",
                None,
                "2026-04-15T00:00:02Z",
                "2026-04-15T00:00:04Z",
                "2026-04-15T00:00:02Z",
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
                    "{}",
                    "2026-04-15T00:00:05Z",
                ),
                (
                    "event-2",
                    goal_two.goal.id,
                    goal_two.root_task.id,
                    "run-2",
                    lead.id,
                    "run.failed",
                    "{}",
                    "2026-04-15T00:00:06Z",
                ),
                (
                    "event-3",
                    goal_one.goal.id,
                    "task-child-1",
                    None,
                    worker.id,
                    "task.started",
                    "{}",
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
        "run_one_id": "run-1",
        "run_two_id": "run-2",
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

            await pilot.press("down")
            await pilot.pause()
            assert app.screen.selected_run_id == ids["run_two_id"]
            assert "task: Ship slice B" in str(detail.content)

    asyncio.run(run_test())


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
