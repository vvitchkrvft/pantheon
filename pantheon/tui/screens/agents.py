"""Agents screen for the Pantheon TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import ListItem, ListView, Static

from pantheon.db import AgentRecord, get_agent_for_tui, list_agents_for_group
from pantheon.tui.screens import PantheonScreen, panel_widget


class AgentsScreen(PantheonScreen):
    """Fleet inspection screen."""

    screen_title = "Agents"
    selected_agent_id: reactive[str | None] = reactive(None)

    def __init__(self) -> None:
        super().__init__()
        self._agents: list[AgentRecord] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="agents-layout", classes="two-panel-layout"):
            yield panel_widget(ListView(), panel_id="agents-list", title="Agent List")
            yield panel_widget(Static("Loading agents..."), panel_id="agents-detail", title="Agent Detail")

    def on_mount(self) -> None:
        self.refresh_screen_data()

    def focus_default(self) -> None:
        self.query_one("#agents-list", ListView).focus()

    def refresh_screen_data(self) -> None:
        list_view = self.query_one("#agents-list", ListView)
        detail = self.query_one("#agents-detail", Static)
        group_id = self.pantheon_app.current_group_id
        list_view.clear()

        if group_id is None:
            self._agents = []
            self.selected_agent_id = None
            detail.update("No groups configured.")
            return

        self._agents = list_agents_for_group(self.pantheon_app.db_path, group_id)
        if not self._agents:
            self.selected_agent_id = None
            detail.update("No agents found in the current group.")
            return

        for agent in self._agents:
            list_view.append(
                ListItem(
                    Static(f"{agent.name} [{agent.role}] {agent.status}"),
                )
            )

        target_index = 0
        if self.selected_agent_id is not None:
            target_index = next(
                (
                    index
                    for index, agent in enumerate(self._agents)
                    if agent.id == self.selected_agent_id
                ),
                0,
            )
        list_view.index = target_index
        self._sync_selection_from_index(target_index)

    def handle_group_changed(self) -> None:
        if self.is_mounted:
            self.selected_agent_id = None
        super().handle_group_changed()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id != "agents-list":
            return
        self._sync_selection_from_index(event.list_view.index)

    def watch_selected_agent_id(self, old_value: str | None, new_value: str | None) -> None:
        detail = self.query_one("#agents-detail", Static)
        if new_value is None:
            if self.pantheon_app.current_group_id is None:
                detail.update("No groups configured.")
            else:
                detail.update("No agents found in the current group.")
            return

        agent = get_agent_for_tui(self.pantheon_app.db_path, new_value)
        detail.update(_format_agent_detail(agent))

    def _sync_selection_from_index(self, index: int | None) -> None:
        if index is None or index < 0 or index >= len(self._agents):
            self.selected_agent_id = None
            return
        self.selected_agent_id = self._agents[index].id


def _format_agent_detail(agent: AgentRecord) -> str:
    profile_name = agent.profile_name or "None"
    model_override = agent.model_override or "None"
    provider_override = agent.provider_override or "None"
    return "\n".join(
        [
            f"name: {agent.name}",
            f"role: {agent.role}",
            f"status: {agent.status}",
            f"profile: {profile_name}",
            f"model_override: {model_override}",
            f"provider_override: {provider_override}",
            f"hermes_home: {agent.hermes_home}",
            f"workdir: {agent.workdir}",
            f"updated_at: {agent.updated_at}",
        ]
    )
