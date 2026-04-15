# Pantheon CLI and TUI Contract

## Purpose

Pantheon is the control plane. Hermes is the agent execution runtime.

This document binds the V1 operator surface. The TUI is the primary product surface. The CLI is secondary and must stay thin, scriptable, and limited to launch, setup, and inspection flows.

## Surface Priority Rule

- The TUI must support the full core product loop.
- The CLI must not become a parallel full-management surface that replaces the TUI.
- The CLI may expose narrow non-interactive commands for setup, launch, and inspection.

The full core loop is:

1. create or load group
2. submit goal
3. start execution
4. watch runs
5. inspect outputs

## Required V1 CLI Commands

The required command surface is:

- `pantheon`
  - launches the TUI

- `pantheon group init <name>`
  - creates a new group

- `pantheon group list`
  - lists saved groups

- `pantheon agent add`
  - adds one agent to an existing group

- `pantheon goal submit "<goal text>" --group <group-name-or-id>`
  - creates one goal and its root lead task

- `pantheon start <goal-id>`
  - starts runner execution for one goal

- `pantheon status <goal-id>`
  - prints compact goal, task, and run state

- `pantheon inspect task <task-id>`
  - prints task detail and latest result text

- `pantheon inspect run <run-id>`
  - prints run metadata and log location

- `pantheon retry task <task-id>`
  - retries one task through explicit operator action

- `pantheon cancel goal <goal-id>`
  - cancels one goal through explicit operator action

No other CLI commands are part of V1.

## CLI Behavior Rules

- CLI commands must use Pantheon persisted state, not ad hoc files
- CLI commands must remain thin wrappers around Pantheon control-plane modules
- CLI output must be deterministic enough for operator use and testing
- CLI must not expose hidden autonomous behavior
- interactive flows are allowed only where the command is explicitly interactive, such as `pantheon agent add`

## First Slice Output Contract

The first implemented CLI slice covers:

- `pantheon group init <name>`
- `pantheon group list`

Their output shape is binding now so tests and later code stay aligned.

### `pantheon group init <name>`

Behavior:

- create one group row
- fail with a non-zero exit if the name already exists or input is invalid

Success output:

- one line only
- includes created group ID and group name

Required format:

```text
created group <id> <name>
```

Failure output:

- concise human-readable error on stderr

### `pantheon group list`

Behavior:

- list all saved groups in stable order
- stable order is ascending `created_at`, then ascending `id`

Success output:

- header row plus one row per group
- stable columns:
  - `id`
  - `name`
  - `created_at`
  - `updated_at`

Required format:

```text
id	name	created_at	updated_at
<id>	<name>	<created_at>	<updated_at>
```

An empty result still prints the header row.

## TUI Required Screens

The TUI must provide these exact V1 screens named in the brief:

- Group picker
- Group detail
- Agent editor
- Goal submit
- Goal detail / execution view
- Task detail panel
- Run detail panel

Operator-pattern language such as overview, fleet, detail, live feed, ledger, and workspace or log inspection is supplementary explanation only. It does not replace the named screen contract above.

## TUI Required Actions

The TUI must support these actions in V1:

- create a group
- load an existing group
- add or edit agents in the group
- mark exactly one agent as lead
- submit a goal
- start execution for a goal
- cancel a goal
- retry a task
- inspect a run
- watch live task and run activity
- inspect final and in-progress task output
- inspect run logs
- inspect goal, task, run, and event history

The TUI must not hide start, stop, inspect, retry, or cancel behind background automation.

## Inspection vs Mutation Rules

Mutation-capable surfaces:

- group creation and editing
- agent creation and editing
- goal submission
- explicit start
- explicit cancel
- explicit retry

Inspection-capable surfaces:

- status views
- goal, task, run, and event detail
- live output feed
- log inspection
- explicit run inspection

Inspection views must not mutate control-plane state except for local UI state such as selection or focus.

## CLI and TUI Vocabulary Rules

- Pantheon must be described as the control plane
- Hermes must be described as the agent execution runtime
- task means work object
- run means execution attempt

The CLI and TUI must not present Pantheon as an autonomous agent or as a multi-runtime system.

## V1 Exclusions

This contract does not add:

- web UI
- remote operator access
- multi-user workflows
- approvals
- budgets
- plugin management
- non-Hermes runtimes
