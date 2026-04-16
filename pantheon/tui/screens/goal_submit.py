"""Modal goal submission flow for the Pantheon TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from pantheon.db import GoalSubmissionRecord, submit_goal

if TYPE_CHECKING:
    from pantheon.tui.app import PantheonApp


class GoalSubmitScreen(ModalScreen[GoalSubmissionRecord | None]):
    """Keyboard-driven modal for submitting one goal to the current group."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("g", "open_group_selector", "Group Selector", show=False),
        Binding("[", "previous_group", "Prev Group", show=False),
        Binding("]", "next_group", "Next Group", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="goal-submit-modal"):
            yield Static("Submit Goal", id="goal-submit-title")
            yield Static(id="goal-submit-group")
            yield Input(
                placeholder="Enter goal text",
                id="goal-submit-input",
            )
            yield Static(
                "Enter submits. Escape cancels. g opens the group selector. [ / ] cycle groups.",
                id="goal-submit-hint",
            )
            yield Static("", id="goal-submit-status")

    def on_mount(self) -> None:
        self._update_group_context()
        self.query_one("#goal-submit-input", Input).focus()

    def on_screen_resume(self) -> None:
        self._update_group_context()
        self.query_one("#goal-submit-input", Input).focus()

    def action_submit(self) -> None:
        group_id = self.pantheon_app.current_group_id
        if group_id is None:
            self._show_error("no current group selected")
            return

        goal_text = self.query_one("#goal-submit-input", Input).value
        if not goal_text.strip():
            self._show_error("goal text must not be empty")
            return

        try:
            submission = submit_goal(
                self.pantheon_app.db_path,
                group_name_or_id=group_id,
                goal_text=goal_text,
            )
        except ValueError as error:
            self._show_error(str(error))
            return

        self.dismiss(submission)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_open_group_selector(self) -> None:
        self.pantheon_app.action_open_group_selector()

    def action_previous_group(self) -> None:
        self.pantheon_app.action_previous_group()
        self._update_group_context()

    def action_next_group(self) -> None:
        self.pantheon_app.action_next_group()
        self._update_group_context()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "goal-submit-input":
            return
        self.action_submit()

    def _show_error(self, message: str) -> None:
        self.query_one("#goal-submit-status", Static).update(f"Error: {message}")

    @property
    def pantheon_app(self) -> PantheonApp:
        return cast("PantheonApp", self.app)

    def _update_group_context(self) -> None:
        status = self.query_one("#goal-submit-status", Static)
        status.update("")
        self.query_one("#goal-submit-group", Static).update(
            f"Current group: {self.pantheon_app.current_group_label()}"
        )
