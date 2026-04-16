"""Goals screen for the Pantheon TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import ListItem, ListView, Static

from pantheon.db import GoalDetailRecord, get_goal_for_tui, list_goals_for_group
from pantheon.tui.screens import PantheonScreen, panel_widget


class GoalsScreen(PantheonScreen):
    """Goal inspection screen."""

    screen_title = "Goals"
    selected_goal_id: reactive[str | None] = reactive(None)

    def __init__(self) -> None:
        super().__init__()
        self._goals: list[GoalDetailRecord] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="goals-layout", classes="two-panel-layout"):
            yield panel_widget(ListView(), panel_id="goals-list", title="Goal List")
            yield panel_widget(Static("Loading goals..."), panel_id="goals-detail", title="Goal Detail")

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
            self.selected_goal_id = None
            detail.update("No groups configured.")
            return

        self._goals = list_goals_for_group(self.pantheon_app.db_path, group_id)
        if not self._goals:
            self.selected_goal_id = None
            detail.update("No goals found in the current group.")
            return

        for goal in self._goals:
            list_view.append(
                ListItem(
                    Static(f"{goal.title} [{goal.status}] tasks={goal.task_count} runs={goal.run_count}"),
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

    def handle_group_changed(self) -> None:
        if self.is_mounted:
            self.selected_goal_id = None
        super().handle_group_changed()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id != "goals-list":
            return
        self._sync_selection_from_index(event.list_view.index)

    def watch_selected_goal_id(self, old_value: str | None, new_value: str | None) -> None:
        detail = self.query_one("#goals-detail", Static)
        if new_value is None:
            if self.pantheon_app.current_group_id is None:
                detail.update("No groups configured.")
            else:
                detail.update("No goals found in the current group.")
            return

        goal = get_goal_for_tui(self.pantheon_app.db_path, new_value)
        detail.update(_format_goal_detail(goal))

    def _sync_selection_from_index(self, index: int | None) -> None:
        if index is None or index < 0 or index >= len(self._goals):
            self.selected_goal_id = None
            return
        self.selected_goal_id = self._goals[index].id


def _format_goal_detail(goal: GoalDetailRecord) -> str:
    root_task_id = goal.root_task_id or "None"
    started_at = goal.started_at or "None"
    completed_at = goal.completed_at or "None"
    return "\n".join(
        [
            f"title: {goal.title}",
            f"status: {goal.status}",
            f"root_task_id: {root_task_id}",
            f"task_count: {goal.task_count}",
            f"run_count: {goal.run_count}",
            f"started_at: {started_at}",
            f"completed_at: {completed_at}",
            f"updated_at: {goal.updated_at}",
        ]
    )
