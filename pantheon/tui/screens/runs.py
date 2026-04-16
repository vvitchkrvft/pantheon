"""Runs screen for the Pantheon TUI."""

from textual.app import ComposeResult
from textual.containers import Horizontal

from pantheon.tui.screens import PlaceholderPanelScreen, labeled_panel


class RunsScreen(PlaceholderPanelScreen):
    """Run inspection screen."""

    screen_title = "Runs"

    def compose_panels(self) -> ComposeResult:
        with Horizontal(id="runs-layout", classes="two-panel-layout"):
            yield labeled_panel(
                panel_id="runs-list",
                title="Run List",
                body="Read-only list placeholder for execution attempts.",
            )
            yield labeled_panel(
                panel_id="runs-detail",
                title="Run Detail / Log Preview",
                body="Selected run metadata and log preview placeholder.",
            )
