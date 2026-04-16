"""Settings screen for the Pantheon TUI."""

from textual.app import ComposeResult
from textual.containers import Grid

from pantheon.tui.screens import PlaceholderPanelScreen, labeled_panel


class SettingsScreen(PlaceholderPanelScreen):
    """Local app information and settings placeholder screen."""

    screen_title = "Settings"

    def compose_panels(self) -> ComposeResult:
        with Grid(id="settings-layout"):
            yield labeled_panel(
                panel_id="settings-app-info",
                title="App Info",
                body="Pantheon is the control plane. Hermes remains the runtime.",
            )
            yield labeled_panel(
                panel_id="settings-database-path",
                title="Database Path",
                body="Database path visibility placeholder.",
            )
            yield labeled_panel(
                panel_id="settings-runtime-notes",
                title="Runtime Notes",
                body="Local runtime notes placeholder.",
            )
            yield labeled_panel(
                panel_id="settings-future-placeholder",
                title="Future Settings Placeholder",
                body="Reserved for later operator preferences.",
            )
