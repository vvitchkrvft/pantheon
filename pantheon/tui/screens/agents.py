"""Agents screen for the Pantheon TUI."""

from textual.app import ComposeResult
from textual.containers import Horizontal

from pantheon.tui.screens import PlaceholderPanelScreen, labeled_panel


class AgentsScreen(PlaceholderPanelScreen):
    """Fleet inspection screen."""

    screen_title = "Agents"

    def compose_panels(self) -> ComposeResult:
        with Horizontal(id="agents-layout", classes="two-panel-layout"):
            yield labeled_panel(
                panel_id="agents-list",
                title="Agent List",
                body="Read-only list placeholder for Pantheon-managed agents.",
            )
            yield labeled_panel(
                panel_id="agents-detail",
                title="Agent Detail",
                body="Selected agent detail placeholder.",
            )
