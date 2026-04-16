"""Modal group selector for the Pantheon TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static

from pantheon.db import GroupRecord
from pantheon.tui.screens import panel_widget


class GroupSelectorScreen(ModalScreen[str | None]):
    """Keyboard-driven modal for explicit group selection."""

    BINDINGS = [
        Binding("enter", "confirm_selection", "Choose", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        groups: list[GroupRecord],
        current_group_id: str | None,
    ) -> None:
        super().__init__()
        self._groups = groups
        self._current_group_id = current_group_id

    def compose(self) -> ComposeResult:
        with Vertical(id="group-selector-modal"):
            yield Static("Choose Group", id="group-selector-title")
            yield panel_widget(ListView(), panel_id="group-selector-list", title="Saved Groups")
            yield Static(
                "Arrow keys move. Enter confirms. Escape cancels.",
                id="group-selector-hint",
            )

    def on_mount(self) -> None:
        list_view = self.query_one("#group-selector-list", ListView)
        for index, group in enumerate(self._groups, start=1):
            current_marker = " *" if group.id == self._current_group_id else ""
            list_view.append(
                ListItem(
                    Static(f"{index}. {group.name} ({group.id}){current_marker}"),
                )
            )

        selected_index = next(
            (index for index, group in enumerate(self._groups) if group.id == self._current_group_id),
            0,
        )
        list_view.index = selected_index
        list_view.focus()

    def action_confirm_selection(self) -> None:
        list_view = self.query_one("#group-selector-list", ListView)
        index = list_view.index
        if index is None or index < 0 or index >= len(self._groups):
            self.dismiss(None)
            return
        self.dismiss(self._groups[index].id)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "group-selector-list":
            return
        self.action_confirm_selection()
