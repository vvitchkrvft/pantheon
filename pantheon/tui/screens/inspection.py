"""Read-only drill-in inspection screens for Pantheon entities."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from pantheon.db import get_goal_for_tui, get_run_for_tui, get_task_for_tui
from pantheon.tui.screens import panel_widget

if TYPE_CHECKING:
    from pantheon.tui.app import PantheonApp


class InspectionScreen(Screen[None]):
    """Shared read-only drill-in pattern for entity inspection."""

    BINDINGS = [
        Binding("escape", "return_to_list", "Back", show=False),
        Binding("backspace", "return_to_list", "Back", show=False),
    ]

    inspection_title = "Inspect"

    @property
    def pantheon_app(self) -> PantheonApp:
        return cast("PantheonApp", self.app)

    def compose(self) -> ComposeResult:
        with Vertical(classes="inspection-layout"):
            yield panel_widget(
                Static(""),
                panel_id="inspection-body",
                title=self.inspection_title,
            )
            yield Static("Escape or Backspace returns to the previous list.", id="inspection-hint")

    def on_mount(self) -> None:
        self.pantheon_app.refresh_shell_context(self.inspection_title)
        self._refresh_body()

    def on_screen_resume(self) -> None:
        self.pantheon_app.refresh_shell_context(self.inspection_title)
        self._refresh_body()

    def action_return_to_list(self) -> None:
        self.pantheon_app.pop_screen()

    def handle_group_changed(self) -> None:
        self.pantheon_app.pop_screen()

    def _refresh_body(self) -> None:
        self.query_one("#inspection-body", Static).update(self.render_body())

    def render_body(self) -> str:
        raise NotImplementedError


class GoalInspectionScreen(InspectionScreen):
    """Focused read-only inspection for one goal."""

    inspection_title = "Goal Inspect"

    def __init__(self, goal_id: str) -> None:
        super().__init__()
        self.goal_id = goal_id

    def render_body(self) -> str:
        goal = get_goal_for_tui(self.pantheon_app.db_path, self.goal_id)
        root_task_id = goal.root_task_id or "None"
        started_at = goal.started_at or "None"
        completed_at = goal.completed_at or "None"
        return "\n".join(
            [
                "entity_type: goal",
                f"id: {goal.id}",
                f"group_id: {goal.group_id}",
                f"title: {goal.title}",
                f"status: {goal.status}",
                f"root_task_id: {root_task_id}",
                f"task_count: {goal.task_count}",
                f"run_count: {goal.run_count}",
                f"created_at: {goal.created_at}",
                f"started_at: {started_at}",
                f"completed_at: {completed_at}",
                f"updated_at: {goal.updated_at}",
            ]
        )


class TaskInspectionScreen(InspectionScreen):
    """Focused read-only inspection for one task."""

    inspection_title = "Task Inspect"

    def __init__(self, task_id: str) -> None:
        super().__init__()
        self.task_id = task_id

    def render_body(self) -> str:
        task = get_task_for_tui(self.pantheon_app.db_path, self.task_id)
        parent_task_id = task.parent_task_id or "None"
        result_text = task.result_text or "None"
        started_at = task.started_at or "None"
        completed_at = task.completed_at or "None"
        return "\n".join(
            [
                "entity_type: task",
                f"id: {task.id}",
                f"goal_id: {task.goal_id}",
                f"parent_task_id: {parent_task_id}",
                f"title: {task.title}",
                f"goal: {task.goal_title}",
                f"assigned_agent_id: {task.assigned_agent_id}",
                f"assigned_agent: {task.assigned_agent_name}",
                f"status: {task.status}",
                f"depth: {task.depth}",
                f"priority: {task.priority}",
                f"input_text: {task.input_text}",
                f"result_text: {result_text}",
                f"created_at: {task.created_at}",
                f"started_at: {started_at}",
                f"completed_at: {completed_at}",
                f"updated_at: {task.updated_at}",
            ]
        )


class RunInspectionScreen(InspectionScreen):
    """Focused read-only inspection for one run."""

    inspection_title = "Run Inspect"

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self.run_id = run_id

    def render_body(self) -> str:
        run = get_run_for_tui(self.pantheon_app.db_path, self.run_id)
        session_id = run.session_id or "None"
        exit_code = "None" if run.exit_code is None else str(run.exit_code)
        error_text = run.error_text or "None"
        started_at = run.started_at or "None"
        finished_at = run.finished_at or "None"
        return "\n".join(
            [
                "entity_type: run",
                f"id: {run.id}",
                f"task_id: {run.task_id}",
                f"agent_id: {run.agent_id}",
                f"task: {run.task_title}",
                f"goal: {run.goal_title}",
                f"agent: {run.agent_name}",
                f"attempt_number: {run.attempt_number}",
                f"status: {run.status}",
                f"session_id: {session_id}",
                f"exit_code: {exit_code}",
                f"error_text: {error_text}",
                f"log_path: {run.log_path}",
                f"created_at: {run.created_at}",
                f"started_at: {started_at}",
                f"finished_at: {finished_at}",
            ]
        )
