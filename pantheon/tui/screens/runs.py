"""Runs screen for the Pantheon TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import ListItem, ListView, Static

from pantheon.db import RunDetailRecord, RunListItemRecord, get_run_for_tui, list_runs_for_group
from pantheon.tui.screens import PantheonScreen, panel_widget
from pantheon.tui.screens.inspection import RunInspectionScreen


class RunsScreen(PantheonScreen):
    """Run inspection screen."""

    BINDINGS = [Binding("enter", "drill_in", "Inspect", show=False)]
    screen_title = "Runs"
    selected_run_id: reactive[str | None] = reactive(None)

    def __init__(self) -> None:
        super().__init__()
        self._runs: list[RunListItemRecord] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="runs-layout", classes="two-panel-layout"):
            yield panel_widget(ListView(), panel_id="runs-list", title="Run List")
            yield panel_widget(Static("Loading runs..."), panel_id="runs-detail", title="Run Detail / Log Preview")

    def on_mount(self) -> None:
        self.refresh_screen_data()

    def focus_default(self) -> None:
        self.query_one("#runs-list", ListView).focus()

    def refresh_screen_data(self) -> None:
        list_view = self.query_one("#runs-list", ListView)
        detail = self.query_one("#runs-detail", Static)
        group_id = self.pantheon_app.current_group_id
        list_view.clear()

        if group_id is None:
            self._runs = []
            self.selected_run_id = None
            detail.update("No groups configured.")
            return

        self._runs = list_runs_for_group(self.pantheon_app.db_path, group_id)
        if not self._runs:
            self.selected_run_id = None
            detail.update("No runs found in the current group.")
            return

        for run in self._runs:
            list_view.append(
                ListItem(
                    Static(f"#{run.attempt_number} {run.task_title} [{run.status}] -> {run.agent_name}"),
                )
            )

        target_index = 0
        if self.selected_run_id is not None:
            target_index = next(
                (
                    index
                    for index, run in enumerate(self._runs)
                    if run.id == self.selected_run_id
                ),
                0,
            )
        list_view.index = target_index
        self._sync_selection_from_index(target_index)

    def handle_group_changed(self) -> None:
        if self.is_mounted:
            self.selected_run_id = None
        super().handle_group_changed()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id != "runs-list":
            return
        self._sync_selection_from_index(event.list_view.index)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "runs-list":
            return
        self.action_drill_in()

    def action_drill_in(self) -> None:
        if self.selected_run_id is None:
            return
        self.app.push_screen(RunInspectionScreen(self.selected_run_id))

    def watch_selected_run_id(self, old_value: str | None, new_value: str | None) -> None:
        detail = self.query_one("#runs-detail", Static)
        if new_value is None:
            if self.pantheon_app.current_group_id is None:
                detail.update("No groups configured.")
            else:
                detail.update("No runs found in the current group.")
            return

        run = get_run_for_tui(self.pantheon_app.db_path, new_value)
        detail.update(_format_run_detail(run))

    def _sync_selection_from_index(self, index: int | None) -> None:
        if index is None or index < 0 or index >= len(self._runs):
            self.selected_run_id = None
            return
        self.selected_run_id = self._runs[index].id


def _format_run_detail(run: RunDetailRecord) -> str:
    session_id = run.session_id or "None"
    exit_code = "None" if run.exit_code is None else str(run.exit_code)
    error_text = run.error_text or "None"
    started_at = run.started_at or "None"
    finished_at = run.finished_at or "None"
    return "\n".join(
        [
            f"task: {run.task_title}",
            f"goal: {run.goal_title}",
            f"agent: {run.agent_name}",
            f"attempt_number: {run.attempt_number}",
            f"status: {run.status}",
            f"session_id: {session_id}",
            f"exit_code: {exit_code}",
            f"error_text: {error_text}",
            f"log_path: {run.log_path}",
            f"log_preview: {run.log_preview_label}",
            run.log_preview_text,
            f"started_at: {started_at}",
            f"finished_at: {finished_at}",
        ]
    )
