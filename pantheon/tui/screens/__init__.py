"""Pantheon TUI screens."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Static


def labeled_panel(*, panel_id: str, title: str, body: str) -> Static:
    """Build a simple titled panel using built-in Textual widgets."""
    panel = Static(f"{title}\n{body}", id=panel_id, classes="panel")
    panel.border_title = title
    return panel


class PantheonScreen(Screen[None]):
    """Base screen for Pantheon's top-level operator surfaces."""

    screen_title = "Pantheon"

    def on_screen_resume(self) -> None:
        self.app.sub_title = self.screen_title
        self.focus_default()

    def focus_default(self) -> None:
        focus_target = self.query("*").first()
        if focus_target is not None:
            focus_target.focus()


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
    "Container",
]
