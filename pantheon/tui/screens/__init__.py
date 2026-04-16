"""Pantheon TUI screens."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from pantheon.tui.app import PantheonApp


def labeled_panel(*, panel_id: str, title: str, body: str) -> Static:
    """Build a simple titled panel using built-in Textual widgets."""
    panel = Static(f"{title}\n{body}", id=panel_id, classes="panel")
    panel.border_title = title
    return panel


def panel_widget(widget: Widget, *, panel_id: str, title: str) -> Widget:
    """Apply Pantheon panel styling to a built-in Textual widget."""
    widget.id = panel_id
    widget.add_class("panel")
    widget.border_title = title
    return widget


class PantheonScreen(Screen[None]):
    """Base screen for Pantheon's top-level operator surfaces."""

    screen_title = "Pantheon"

    def on_screen_resume(self) -> None:
        self.app.sub_title = self.screen_title
        self.focus_default()
        self.refresh_screen_data()

    def focus_default(self) -> None:
        focus_target = self.query("*").first()
        if focus_target is not None:
            focus_target.focus()

    @property
    def pantheon_app(self) -> PantheonApp:
        return cast("PantheonApp", self.app)

    def refresh_screen_data(self) -> None:
        """Reload any read-only data needed by the screen."""


class PlaceholderPanelScreen(PantheonScreen):
    """Shared composition pattern for simple placeholder shells."""

    def compose(self) -> ComposeResult:
        yield from self.compose_panels()

    def compose_panels(self) -> ComposeResult:
        raise NotImplementedError


__all__ = [
    "PantheonScreen",
    "PlaceholderPanelScreen",
    "labeled_panel",
    "panel_widget",
    "Container",
]
