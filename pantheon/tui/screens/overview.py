"""Overview screen for the Pantheon TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid
from textual.widgets import Static

from pantheon.db import (
    get_overview_summary,
    get_recent_events_for_group,
    list_agents_for_group,
)
from pantheon.tui.screens import PlaceholderPanelScreen, labeled_panel


class OverviewScreen(PlaceholderPanelScreen):
    """Top-level control-plane summary screen."""

    screen_title = "Overview"

    def on_mount(self) -> None:
        self.refresh_screen_data()

    def compose_panels(self) -> ComposeResult:
        with Grid(id="overview-layout"):
            yield labeled_panel(
                panel_id="overview-primary-readout",
                title="Primary Readout",
                body="Loading current group summary...",
            )
            yield labeled_panel(
                panel_id="overview-live-feed",
                title="Live Feed",
                body="Live run output will land here in a later slice.",
            )
            yield labeled_panel(
                panel_id="overview-agents",
                title="Agents",
                body="Loading current group agents...",
            )
            yield labeled_panel(
                panel_id="overview-group-topology",
                title="Group Topology",
                body="Group topology placeholder for the current operator context.",
            )
            yield labeled_panel(
                panel_id="overview-recent-activity",
                title="Recent Activity",
                body="Loading recent activity...",
            )

    def refresh_screen_data(self) -> None:
        primary = self.query_one("#overview-primary-readout", Static)
        agents_panel = self.query_one("#overview-agents", Static)
        recent_activity = self.query_one("#overview-recent-activity", Static)
        group_id = self.pantheon_app.current_group_id

        if group_id is None:
            empty_text = (
                "No groups configured.\n"
                "Create a group from the CLI before using the read-only inspection screens."
            )
            primary.update(empty_text)
            agents_panel.update("No current group selected.")
            recent_activity.update("No recent activity available.")
            return

        summary = get_overview_summary(self.pantheon_app.db_path, group_id)
        primary.update(_format_primary_readout(summary))

        agents = list_agents_for_group(self.pantheon_app.db_path, group_id)
        if agents:
            agents_panel.update(
                "\n".join(
                    f"{agent.name} [{agent.role}] {agent.status}" for agent in agents[:6]
                )
            )
        else:
            agents_panel.update("No agents found in the current group.")

        events = get_recent_events_for_group(self.pantheon_app.db_path, group_id, limit=6)
        if events:
            recent_activity.update(
                "\n".join(
                    f"{event.created_at} {event.event_type}" for event in events
                )
            )
        else:
            recent_activity.update("No recent activity recorded for the current group.")


def _format_primary_readout(summary) -> str:
    return "\n".join(
        [
            f"group: {summary.group_name}",
            f"agents: {summary.agent_count}",
            f"goals: {summary.goal_count} active={summary.active_goal_count}",
            f"tasks: {summary.task_count} active={summary.active_task_count}",
            f"runs: {summary.run_count} active={summary.active_run_count}",
        ]
    )
