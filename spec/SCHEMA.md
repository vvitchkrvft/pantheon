# Pantheon Schema Contract

## Purpose

Pantheon is the control plane. Hermes is the agent execution runtime.

This document binds the SQLite schema Pantheon uses to persist V1 control-plane state. SQLite is the only source of truth. Groups, agents, goals, tasks, runs, and events must be stored in this schema.

## Storage Standards

- Database engine: SQLite
- ID shape: `TEXT` primary keys
- ID format rule: application-generated opaque string IDs; UUID format is allowed but not required by SQLite itself
- Timestamp shape: UTC ISO 8601 text
- Boolean shape: `INTEGER` constrained to `0` or `1` only when a boolean is needed
- JSON payload shape: `TEXT` containing serialized JSON

## Table Definitions

### `groups`

Purpose: saved operator-defined group of Hermes agents.

Columns:

| column | type | null | constraints |
| --- | --- | --- | --- |
| `id` | `TEXT` | no | primary key |
| `name` | `TEXT` | no | unique |
| `created_at` | `TEXT` | no | UTC ISO 8601 |
| `updated_at` | `TEXT` | no | UTC ISO 8601 |

### `agents`

Purpose: Hermes agent configuration owned by one group.

Columns:

| column | type | null | constraints |
| --- | --- | --- | --- |
| `id` | `TEXT` | no | primary key |
| `group_id` | `TEXT` | no | references `groups(id)` on delete cascade |
| `name` | `TEXT` | no | unique within group |
| `role` | `TEXT` | no | `lead` or `worker` |
| `profile_name` | `TEXT` | yes | Hermes profile name |
| `hermes_home` | `TEXT` | no | absolute or operator-provided path |
| `workdir` | `TEXT` | no | absolute or operator-provided path |
| `model_override` | `TEXT` | yes | nullable |
| `provider_override` | `TEXT` | yes | nullable |
| `status` | `TEXT` | no | `idle`, `busy`, `disabled`, or `error` |
| `created_at` | `TEXT` | no | UTC ISO 8601 |
| `updated_at` | `TEXT` | no | UTC ISO 8601 |

### `goals`

Purpose: top-level operator work item scoped to one group.

Columns:

| column | type | null | constraints |
| --- | --- | --- | --- |
| `id` | `TEXT` | no | primary key |
| `group_id` | `TEXT` | no | references `groups(id)` on delete cascade |
| `title` | `TEXT` | no | operator-submitted goal text or title |
| `status` | `TEXT` | no | `draft`, `queued`, `running`, `complete`, `failed`, or `cancelled` |
| `root_task_id` | `TEXT` | yes | references `tasks(id)` on delete set null |
| `started_at` | `TEXT` | yes | UTC ISO 8601 |
| `completed_at` | `TEXT` | yes | UTC ISO 8601 |
| `created_at` | `TEXT` | no | UTC ISO 8601 |
| `updated_at` | `TEXT` | no | UTC ISO 8601 |

### `tasks`

Purpose: work object under one goal. A task is not a run.

Columns:

| column | type | null | constraints |
| --- | --- | --- | --- |
| `id` | `TEXT` | no | primary key |
| `goal_id` | `TEXT` | no | references `goals(id)` on delete cascade |
| `parent_task_id` | `TEXT` | yes | references `tasks(id)` on delete restrict |
| `assigned_agent_id` | `TEXT` | no | references `agents(id)` on delete restrict |
| `title` | `TEXT` | no | short task title |
| `input_text` | `TEXT` | no | concrete task instruction |
| `result_text` | `TEXT` | yes | latest terminal result text |
| `status` | `TEXT` | no | `queued`, `running`, `complete`, `failed`, or `cancelled` |
| `priority` | `INTEGER` | no | default `5` |
| `depth` | `INTEGER` | no | default `0`, must be `>= 0` |
| `created_at` | `TEXT` | no | UTC ISO 8601 |
| `started_at` | `TEXT` | yes | UTC ISO 8601 |
| `completed_at` | `TEXT` | yes | UTC ISO 8601 |
| `updated_at` | `TEXT` | no | UTC ISO 8601 |

### `runs`

Purpose: one execution attempt for one task on one agent.

Columns:

| column | type | null | constraints |
| --- | --- | --- | --- |
| `id` | `TEXT` | no | primary key |
| `task_id` | `TEXT` | no | references `tasks(id)` on delete cascade |
| `agent_id` | `TEXT` | no | references `agents(id)` on delete restrict |
| `attempt_number` | `INTEGER` | no | must be `>= 1`, unique per task |
| `status` | `TEXT` | no | `queued`, `running`, `complete`, `failed`, or `cancelled` |
| `session_id` | `TEXT` | yes | Hermes session identifier if available |
| `pid` | `INTEGER` | yes | local process id if available |
| `exit_code` | `INTEGER` | yes | nullable until process exits |
| `error_text` | `TEXT` | yes | terminal error summary |
| `log_path` | `TEXT` | no | path to persisted raw run log |
| `usage_json` | `TEXT` | yes | serialized usage payload |
| `started_at` | `TEXT` | yes | UTC ISO 8601 |
| `finished_at` | `TEXT` | yes | UTC ISO 8601 |
| `created_at` | `TEXT` | no | UTC ISO 8601 |

### `events`

Purpose: durable audit trail for meaningful control-plane state transitions.

Columns:

| column | type | null | constraints |
| --- | --- | --- | --- |
| `id` | `TEXT` | no | primary key |
| `goal_id` | `TEXT` | yes | references `goals(id)` on delete cascade |
| `task_id` | `TEXT` | yes | references `tasks(id)` on delete cascade |
| `run_id` | `TEXT` | yes | references `runs(id)` on delete cascade |
| `agent_id` | `TEXT` | yes | references `agents(id)` on delete cascade |
| `event_type` | `TEXT` | no | event discriminator |
| `payload_json` | `TEXT` | no | serialized event payload |
| `created_at` | `TEXT` | no | UTC ISO 8601 |

## SQL Constraints

The following constraints must be represented directly in schema SQL:

- Primary keys on every table
- Foreign keys exactly as declared above
- `UNIQUE(groups.name)`
- `UNIQUE(agents.group_id, agents.name)`
- `UNIQUE(runs.task_id, runs.attempt_number)`
- `CHECK(agents.role IN ('lead', 'worker'))`
- `CHECK(agents.status IN ('idle', 'busy', 'disabled', 'error'))`
- `CHECK(goals.status IN ('draft', 'queued', 'running', 'complete', 'failed', 'cancelled'))`
- `CHECK(tasks.status IN ('queued', 'running', 'complete', 'failed', 'cancelled'))`
- `CHECK(runs.status IN ('queued', 'running', 'complete', 'failed', 'cancelled'))`
- `CHECK(tasks.priority >= 0)`
- `CHECK(tasks.depth >= 0)`
- `CHECK(runs.attempt_number >= 1)`

## Required Indexes

Pantheon must create these indexes in V1:

- `idx_agents_group_id` on `agents(group_id)`
- `idx_goals_group_id` on `goals(group_id)`
- `idx_tasks_goal_id` on `tasks(goal_id)`
- `idx_tasks_parent_task_id` on `tasks(parent_task_id)`
- `idx_tasks_assigned_agent_status` on `tasks(assigned_agent_id, status)`
- `idx_tasks_goal_status` on `tasks(goal_id, status)`
- `idx_tasks_dispatch_order` on `tasks(status, depth, priority, created_at)`
- `idx_runs_task_id` on `runs(task_id)`
- `idx_runs_agent_id_status` on `runs(agent_id, status)`
- `idx_events_goal_created_at` on `events(goal_id, created_at)`
- `idx_events_task_created_at` on `events(task_id, created_at)`
- `idx_events_run_created_at` on `events(run_id, created_at)`

## Invariants Enforced In Python

The following rules are binding and must be enforced by Pantheon application logic rather than direct SQL constraints:

- Each group has exactly one lead agent
- A goal root task must belong to the same goal
- A task parent must belong to the same goal as the child
- A task assigned agent must belong to the same group as the goal
- Root task depth is `0`
- Child task depth is parent depth plus `1`
- A run’s `agent_id` must match the assigned agent for the task being executed
- Only one active run per agent
- Goal completion requires both:
  - a valid lead-agent `completion_judgment`
  - all tasks for the goal in terminal state

## Deferred From This Contract

The following items are intentionally deferred:

- Migration framework choice and migration file layout
- SQLite triggers
- Partial indexes for active-run enforcement
- Full-text search
- Artifact tables beyond `result_text`, `log_path`, and `usage_json`
- Additional denormalized summary columns
- Multi-runtime support
- Multi-user or remote execution concerns

## First Slice Notes

For the first CLI group slice, implementation may stage behavior table by table. The full V1 schema remains binding. The `one active run per agent` invariant remains binding but does not need full enforcement before run creation exists.
