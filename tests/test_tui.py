import asyncio
from pathlib import Path

from textual.widgets import Static

from pantheon.tui import PantheonApp


SCREEN_BINDINGS = (
    (
        "1",
        "overview",
        (
            ("overview-primary-readout", "Primary Readout"),
            ("overview-live-feed", "Live Feed"),
            ("overview-agents", "Agents"),
            ("overview-group-topology", "Group Topology"),
            ("overview-recent-activity", "Recent Activity"),
        ),
    ),
    ("2", "agents", (("agents-list", "Agent List"), ("agents-detail", "Agent Detail"))),
    ("3", "goals", (("goals-list", "Goal List"), ("goals-detail", "Goal Detail"))),
    ("4", "tasks", (("tasks-list", "Task List"), ("tasks-detail", "Task Detail"))),
    (
        "5",
        "runs",
        (("runs-list", "Run List"), ("runs-detail", "Run Detail / Log Preview")),
    ),
    (
        "6",
        "settings",
        (
            ("settings-app-info", "App Info"),
            ("settings-database-path", "Database Path"),
            ("settings-runtime-notes", "Runtime Notes"),
            ("settings-future-placeholder", "Future Settings Placeholder"),
        ),
    ),
)


def test_app_launches_into_overview_screen(tmp_path: Path) -> None:
    async def run_test() -> None:
        app = PantheonApp(tmp_path / "pantheon.db")
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.current_screen_name == "overview"
            assert app.sub_title == "Overview"
            assert app.screen.query_one("#overview-primary-readout", Static)

    asyncio.run(run_test())


def test_top_level_screen_switching_uses_bindings(tmp_path: Path) -> None:
    async def run_test() -> None:
        app = PantheonApp(tmp_path / "pantheon.db")
        async with app.run_test() as pilot:
            for key, expected_screen, panel_ids in SCREEN_BINDINGS:
                await pilot.press(key)
                await pilot.pause()
                assert app.current_screen_name == expected_screen
                for panel_id, _ in panel_ids:
                    assert app.screen.query_one(f"#{panel_id}", Static)

    asyncio.run(run_test())


def test_each_screen_renders_labeled_placeholder_panels(tmp_path: Path) -> None:
    async def run_test() -> None:
        app = PantheonApp(tmp_path / "pantheon.db")
        async with app.run_test() as pilot:
            for key, expected_screen, panel_ids in SCREEN_BINDINGS:
                await pilot.press(key)
                await pilot.pause()
                assert app.current_screen_name == expected_screen
                for panel_id, expected_title in panel_ids:
                    panel = app.screen.query_one(f"#{panel_id}", Static)
                    assert panel.border_title
                    assert str(panel.border_title) == expected_title

    asyncio.run(run_test())
