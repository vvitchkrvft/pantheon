"""Tasks screen for the Pantheon TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import ListItem, ListView, Static

from pantheon.db import TaskDetailRecord, TaskListItemRecord, get_task_for_tui, list_tasks_for_group
from pantheon.tui.screens import PantheonScreen, panel_widget
from pantheon.tui.screens.inspection import TaskInspectionScreen


class TasksScreen(PantheonScreen):
    """Task inspection screen."""

    BINDINGS = [Binding("enter", "drill_in", "Inspect", show=False)]
    screen_title = "Tasks"
    selected_task_id: reactive[str | None] = reactive(None)

    def __init__(self) -> None:
        super().__init__()
        self._tasks: list[TaskListItemRecord] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="tasks-layout", classes="two-panel-layout"):
            yield panel_widget(ListView(), panel_id="tasks-list", title="Task List")
            yield panel_widget(Static("Loading tasks..."), panel_id="tasks-detail", title="Task Detail")

    def on_mount(self) -> None:
        self.refresh_screen_data()

    def focus_default(self) -> None:
        self.query_one("#tasks-list", ListView).focus()

    def refresh_screen_data(self) -> None:
        list_view = self.query_one("#tasks-list", ListView)
        detail = self.query_one("#tasks-detail", Static)
        group_id = self.pantheon_app.current_group_id
        list_view.clear()

        if group_id is None:
            self._tasks = []
            self.selected_task_id = None
            detail.update("No groups configured.")
            return

        self._tasks = list_tasks_for_group(self.pantheon_app.db_path, group_id)
        if not self._tasks:
            self.selected_task_id = None
            detail.update("No tasks found in the current group.")
            return

        for task in self._tasks:
            list_view.append(
                ListItem(
                    Static(f"d{task.depth} {task.title} [{task.status}] -> {task.assigned_agent_name}"),
                )
            )

        target_index = 0
        if self.selected_task_id is not None:
            target_index = next(
                (
                    index
                    for index, task in enumerate(self._tasks)
                    if task.id == self.selected_task_id
                ),
                0,
            )
        list_view.index = target_index
        self._sync_selection_from_index(target_index)

    def handle_group_changed(self) -> None:
        if self.is_mounted:
            self.selected_task_id = None
        super().handle_group_changed()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id != "tasks-list":
            return
        self._sync_selection_from_index(event.list_view.index)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "tasks-list":
            return
        self.action_drill_in()

    def action_drill_in(self) -> None:
        if self.selected_task_id is None:
            return
        self.app.push_screen(TaskInspectionScreen(self.selected_task_id))

    def watch_selected_task_id(self, old_value: str | None, new_value: str | None) -> None:
        detail = self.query_one("#tasks-detail", Static)
        if new_value is None:
            if self.pantheon_app.current_group_id is None:
                detail.update("No groups configured.")
            else:
                detail.update("No tasks found in the current group.")
            return

        task = get_task_for_tui(self.pantheon_app.db_path, new_value)
        detail.update(_format_task_detail(task))

    def _sync_selection_from_index(self, index: int | None) -> None:
        if index is None or index < 0 or index >= len(self._tasks):
            self.selected_task_id = None
            return
        self.selected_task_id = self._tasks[index].id


def _format_task_detail(task: TaskDetailRecord) -> str:
    parent_task_id = task.parent_task_id or "None"
    started_at = task.started_at or "None"
    completed_at = task.completed_at or "None"
    result_text = task.result_text or "None"
    return "\n".join(
        [
            f"title: {task.title}",
            f"status: {task.status}",
            f"goal: {task.goal_title}",
            f"assigned_agent: {task.assigned_agent_name}",
            f"depth: {task.depth}",
            f"priority: {task.priority}",
            f"parent_task_id: {parent_task_id}",
            f"input_text: {task.input_text}",
            f"result_text: {result_text}",
            f"started_at: {started_at}",
            f"completed_at: {completed_at}",
        ]
    )
