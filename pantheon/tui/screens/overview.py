"""Overview screen for the Pantheon TUI."""

from textual.app import ComposeResult
from textual.containers import Grid

from pantheon.tui.screens import PlaceholderPanelScreen, labeled_panel


class OverviewScreen(PlaceholderPanelScreen):
    """Top-level control-plane summary screen."""

    screen_title = "Overview"

    def compose_panels(self) -> ComposeResult:
        with Grid(id="overview-layout"):
            yield labeled_panel(
                panel_id="overview-primary-readout",
                title="Primary Readout",
                body="Read-only summary placeholder for the current Pantheon group.",
            )
            yield labeled_panel(
                panel_id="overview-live-feed",
                title="Live Feed",
                body="Live run output will land here in a later slice.",
            )
            yield labeled_panel(
                panel_id="overview-agents",
                title="Agents",
                body="Compact agent status overview placeholder.",
            )
            yield labeled_panel(
                panel_id="overview-group-topology",
                title="Group Topology",
                body="Group topology placeholder for the current operator context.",
            )
            yield labeled_panel(
                panel_id="overview-recent-activity",
                title="Recent Activity",
                body="Recent event stream placeholder.",
            )
