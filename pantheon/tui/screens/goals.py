"""Goals screen for the Pantheon TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import ListItem, ListView, Static

from pantheon.db import (
    GoalDetailRecord,
    GoalStartabilityRecord,
    get_goal_for_tui,
    get_goal_startability_for_tui,
    list_goals_for_group,
)
from pantheon.tui.screens import PantheonScreen, panel_widget
from pantheon.tui.screens.inspection import GoalInspectionScreen


class GoalsScreen(PantheonScreen):
    """Goal inspection screen."""

    BINDINGS = [
        Binding("enter", "drill_in", "Inspect", show=False),
        Binding("s", "start_goal", "Start"),
    ]
    screen_title = "Goals"
    selected_goal_id: reactive[str | None] = reactive(None)

    def __init__(self) -> None:
        super().__init__()
        self._goals: list[GoalDetailRecord] = []
        self._startability_by_goal_id: dict[str, GoalStartabilityRecord] = {}

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id="goals-layout", classes="two-panel-layout"):
                yield panel_widget(ListView(), panel_id="goals-list", title="Goal List")
                yield panel_widget(Static("Loading goals..."), panel_id="goals-detail", title="Goal Detail")
            yield Static("", id="goals-status")

    def on_mount(self) -> None:
        self.refresh_screen_data()

    def focus_default(self) -> None:
        self.query_one("#goals-list", ListView).focus()

    def refresh_screen_data(self) -> None:
        list_view = self.query_one("#goals-list", ListView)
        detail = self.query_one("#goals-detail", Static)
        group_id = self.pantheon_app.current_group_id
        list_view.clear()

        if group_id is None:
            self._goals = []
            self._startability_by_goal_id = {}
            self.selected_goal_id = None
            detail.update("No groups configured.")
            self._set_status("")
            return

        self._goals = list_goals_for_group(self.pantheon_app.db_path, group_id)
        self._startability_by_goal_id = {
            goal.id: get_goal_startability_for_tui(self.pantheon_app.db_path, goal.id)
            for goal in self._goals
        }
        if not self._goals:
            self.selected_goal_id = None
            detail.update("No goals found in the current group.")
            self._set_status("")
            return

        for goal in self._goals:
            startability = self._startability_by_goal_id[goal.id]
            list_view.append(
                ListItem(
                    Static(
                        f"{goal.title} [{goal.status}] tasks={goal.task_count} "
                        f"runs={goal.run_count} start={'ready' if startability.is_startable else 'blocked'}"
                    ),
                )
            )

        target_index = 0
        if self.selected_goal_id is not None:
            target_index = next(
                (
                    index
                    for index, goal in enumerate(self._goals)
                    if goal.id == self.selected_goal_id
                ),
                0,
            )
        list_view.index = target_index
        self._sync_selection_from_index(target_index)
        if self.selected_goal_id is not None:
            startability = self._startability_by_goal_id[self.selected_goal_id]
            detail.update(
                _format_goal_detail(
                    get_goal_for_tui(self.pantheon_app.db_path, self.selected_goal_id),
                    startability,
                )
            )

    def handle_group_changed(self) -> None:
        if self.is_mounted:
            self.selected_goal_id = None
            self._set_status("")
        super().handle_group_changed()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id != "goals-list":
            return
        self._sync_selection_from_index(event.list_view.index)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "goals-list":
            return
        self.action_drill_in()

    def action_drill_in(self) -> None:
        if self.selected_goal_id is None:
            return
        self.app.push_screen(GoalInspectionScreen(self.selected_goal_id))

    def action_start_goal(self) -> None:
        if self.selected_goal_id is None:
            self._set_status("Error: no goal selected")
            return

        startability = get_goal_startability_for_tui(
            self.pantheon_app.db_path, self.selected_goal_id
        )
        if not startability.is_startable:
            self._set_status(f"Error: {startability.reason}")
            self.refresh_screen_data()
            return

        try:
            result = self.pantheon_app.start_goal(self.selected_goal_id)
        except ValueError as error:
            self._set_status(f"Error: {error}")
            self.refresh_screen_data()
            return

        self._set_status(f"Started goal {result.goal_id}.")

    def watch_selected_goal_id(self, old_value: str | None, new_value: str | None) -> None:
        try:
            detail = self.query_one("#goals-detail", Static)
        except NoMatches:
            return
        if new_value is None:
            if self.pantheon_app.current_group_id is None:
                detail.update("No groups configured.")
            else:
                detail.update("No goals found in the current group.")
            return

        goal = get_goal_for_tui(self.pantheon_app.db_path, new_value)
        startability = get_goal_startability_for_tui(self.pantheon_app.db_path, new_value)
        detail.update(_format_goal_detail(goal, startability))

    def _sync_selection_from_index(self, index: int | None) -> None:
        if index is None or index < 0 or index >= len(self._goals):
            self.selected_goal_id = None
            return
        self.selected_goal_id = self._goals[index].id

    def _set_status(self, message: str) -> None:
        self.query_one("#goals-status", Static).update(message)


def _format_goal_detail(
    goal: GoalDetailRecord, startability: GoalStartabilityRecord
) -> str:
    root_task_id = goal.root_task_id or "None"
    started_at = goal.started_at or "None"
    completed_at = goal.completed_at or "None"
    start_action = (
        "available (press s)"
        if startability.is_startable
        else f"unavailable ({startability.reason})"
    )
    return "\n".join(
        [
            f"title: {goal.title}",
            f"status: {goal.status}",
            f"start_action: {start_action}",
            f"root_task_id: {root_task_id}",
            f"task_count: {goal.task_count}",
            f"run_count: {goal.run_count}",
            f"started_at: {started_at}",
            f"completed_at: {completed_at}",
            f"updated_at: {goal.updated_at}",
        ]
    )
