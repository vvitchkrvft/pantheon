"""Textual application shell for Pantheon."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Footer, Header

from pantheon.db import PathLike, bootstrap_database, resolve_current_group_id
from pantheon.tui.screens.agents import AgentsScreen
from pantheon.tui.screens.goals import GoalsScreen
from pantheon.tui.screens.overview import OverviewScreen
from pantheon.tui.screens.runs import RunsScreen
from pantheon.tui.screens.settings import SettingsScreen
from pantheon.tui.screens.tasks import TasksScreen

SCREEN_ORDER: tuple[tuple[str, str], ...] = (
    ("overview", "Overview"),
    ("agents", "Agents"),
    ("goals", "Goals"),
    ("tasks", "Tasks"),
    ("runs", "Runs"),
    ("settings", "Settings"),
)


class PantheonApp(App[None]):
    """Keyboard-centric TUI shell for Pantheon."""

    CSS_PATH = "pantheon.tcss"
    TITLE = "Pantheon"
    SUB_TITLE = "Overview"
    BINDINGS = [
        Binding("1", "go_to_screen('overview')", "Overview"),
        Binding("2", "go_to_screen('agents')", "Agents"),
        Binding("3", "go_to_screen('goals')", "Goals"),
        Binding("4", "go_to_screen('tasks')", "Tasks"),
        Binding("5", "go_to_screen('runs')", "Runs"),
        Binding("6", "go_to_screen('settings')", "Settings"),
        Binding("q", "quit", "Quit"),
    ]

    current_group_id: reactive[str | None] = reactive(None)
    current_screen_name: reactive[str] = reactive("overview")

    def __init__(self, db_path: PathLike = Path("pantheon.db")) -> None:
        self.db_path = Path(db_path)
        bootstrap_database(self.db_path)
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Footer()

    def on_mount(self) -> None:
        self.current_group_id = resolve_current_group_id(self.db_path)
        self.install_screen(OverviewScreen(), name="overview")
        self.install_screen(AgentsScreen(), name="agents")
        self.install_screen(GoalsScreen(), name="goals")
        self.install_screen(TasksScreen(), name="tasks")
        self.install_screen(RunsScreen(), name="runs")
        self.install_screen(SettingsScreen(), name="settings")
        self.push_screen("overview")
        self.current_screen_name = "overview"
        self.sub_title = "Overview"

    def action_go_to_screen(self, screen_name: str) -> None:
        if screen_name not in dict(SCREEN_ORDER):
            return
        self.switch_screen(screen_name)
        self.current_screen_name = screen_name
        self.sub_title = dict(SCREEN_ORDER)[screen_name]
