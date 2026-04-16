"""Goals screen for the Pantheon TUI."""

from textual.app import ComposeResult
from textual.containers import Horizontal

from pantheon.tui.screens import PlaceholderPanelScreen, labeled_panel


class GoalsScreen(PlaceholderPanelScreen):
    """Goal inspection screen."""

    screen_title = "Goals"

    def compose_panels(self) -> ComposeResult:
        with Horizontal(id="goals-layout", classes="two-panel-layout"):
            yield labeled_panel(
                panel_id="goals-list",
                title="Goal List",
                body="Read-only list placeholder for saved goals.",
            )
            yield labeled_panel(
                panel_id="goals-detail",
                title="Goal Detail",
                body="Selected goal detail placeholder.",
            )
