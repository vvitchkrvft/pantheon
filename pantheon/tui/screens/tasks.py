"""Tasks screen for the Pantheon TUI."""

from textual.app import ComposeResult
from textual.containers import Horizontal

from pantheon.tui.screens import PlaceholderPanelScreen, labeled_panel


class TasksScreen(PlaceholderPanelScreen):
    """Task inspection screen."""

    screen_title = "Tasks"

    def compose_panels(self) -> ComposeResult:
        with Horizontal(id="tasks-layout", classes="two-panel-layout"):
            yield labeled_panel(
                panel_id="tasks-list",
                title="Task List",
                body="Read-only list placeholder for work objects.",
            )
            yield labeled_panel(
                panel_id="tasks-detail",
                title="Task Detail",
                body="Selected task detail placeholder.",
            )
