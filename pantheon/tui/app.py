"""Textual application shell for Pantheon."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Footer, Header, Static

from pantheon.db import GroupRecord, PathLike, bootstrap_database, list_groups, resolve_current_group_id
from pantheon.tui.screens.agents import AgentsScreen
from pantheon.tui.screens.goals import GoalsScreen
from pantheon.tui.screens.group_selector import GroupSelectorScreen
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
        Binding("g", "open_group_selector", "Group Selector"),
        Binding("[", "previous_group", "Prev Group"),
        Binding("]", "next_group", "Next Group"),
        Binding("q", "quit", "Quit"),
    ]

    current_group_id: reactive[str | None] = reactive(None)
    current_screen_name: reactive[str] = reactive("overview")

    def __init__(self, db_path: PathLike = Path("pantheon.db")) -> None:
        self.db_path = Path(db_path)
        bootstrap_database(self.db_path)
        self._groups: list[GroupRecord] = []
        self._screens = {
            "overview": OverviewScreen(),
            "agents": AgentsScreen(),
            "goals": GoalsScreen(),
            "tasks": TasksScreen(),
            "runs": RunsScreen(),
            "settings": SettingsScreen(),
        }
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(id="current-group-context")
        yield Footer()

    def on_mount(self) -> None:
        self._reload_groups()
        self.current_group_id = resolve_current_group_id(self.db_path)
        for name, screen in self._screens.items():
            self.install_screen(screen, name=name)
        self.push_screen("overview")
        self.current_screen_name = "overview"
        self._update_shell_context()

    def action_go_to_screen(self, screen_name: str) -> None:
        if screen_name not in dict(SCREEN_ORDER):
            return
        self.switch_screen(screen_name)
        self.current_screen_name = screen_name
        self.refresh_shell_context()

    def action_previous_group(self) -> None:
        self._cycle_group(-1)

    def action_next_group(self) -> None:
        self._cycle_group(1)

    def action_open_group_selector(self) -> None:
        self._reload_groups()
        if not self._groups:
            return
        self.push_screen(
            GroupSelectorScreen(self._groups, self.current_group_id),
            callback=self._handle_group_selector_dismissed,
        )

    def watch_current_group_id(self, old_value: str | None, new_value: str | None) -> None:
        if old_value == new_value:
            return
        self.refresh_shell_context()
        for screen in self._screens.values():
            screen.handle_group_changed()
        active_screen = self.screen
        handle_group_changed = getattr(active_screen, "handle_group_changed", None)
        if active_screen not in self._screens.values() and callable(handle_group_changed):
            handle_group_changed()

    def _reload_groups(self) -> None:
        self._groups = list_groups(self.db_path)

    def _cycle_group(self, direction: int) -> None:
        self._reload_groups()
        if not self._groups:
            self.current_group_id = None
            return

        current_index = 0
        if self.current_group_id is not None:
            current_index = next(
                (index for index, group in enumerate(self._groups) if group.id == self.current_group_id),
                0,
            )

        target_index = (current_index + direction) % len(self._groups)
        self.select_group(self._groups[target_index].id)

    def select_group(self, group_id: str | None) -> None:
        if group_id is None:
            self.current_group_id = None
            return
        self._reload_groups()
        if any(group.id == group_id for group in self._groups):
            self.current_group_id = group_id

    def _handle_group_selector_dismissed(self, selected_group_id: str | None) -> None:
        if selected_group_id is None:
            return
        self.select_group(selected_group_id)

    def refresh_shell_context(self, screen_title: str | None = None) -> None:
        self._update_shell_context(screen_title=screen_title)

    def _update_shell_context(self, screen_title: str | None = None) -> None:
        screen_title = screen_title or dict(SCREEN_ORDER).get(self.current_screen_name, "Overview")
        group_label = self._current_group_label()
        self.sub_title = screen_title
        if self.is_mounted:
            self.query_one("#current-group-context", Static).update(
                f"Current Group: {group_label}    g open selector    [ / ] cycle groups"
            )

    def _current_group_label(self) -> str:
        self._reload_groups()
        if not self._groups or self.current_group_id is None:
            return "none"

        for index, group in enumerate(self._groups, start=1):
            if group.id == self.current_group_id:
                return f"{group.name} ({index}/{len(self._groups)})"

        return "none"
