# Pantheon Runner Contract

## Purpose

Pantheon is the control plane. Hermes is the agent execution runtime.

This document defines the V1 runner semantics Pantheon must implement around queued tasks, runs, agent state, event emission, and goal progression. The runner is control-plane logic. It does not move into Hermes and does not move into the TUI.

## Scope

The runner is responsible for:

- finding queued tasks for a running goal
- checking agent availability
- creating run records
- invoking the Hermes adapter
- handling stream events
- applying terminal run outcomes
- validating lead-agent control payloads
- creating child tasks from valid lead-agent proposals
- determining whether a goal may become terminal

The runner is not responsible for:

- group creation
- agent editing UX
- database migration strategy
- TUI rendering details

## Dispatch Preconditions

Before Pantheon starts a run for a task, all of the following must be true:

- the goal is in `running`
- the task is in `queued`
- the assigned agent exists
- the assigned agent belongs to the goal’s group
- the assigned agent status is `idle`
- the assigned agent has no active run

An active run is any run whose status is `queued` or `running`.

## Task Selection Order

The runner selects eligible queued tasks in this stable order:

1. lower `depth`
2. lower `priority`
3. earlier `created_at`
4. lower lexical `id` as the final tie-breaker

The runner must not assign a queued task to an agent other than `assigned_agent_id`.

## Run Creation Semantics

When the runner claims a task:

1. resolve the next `attempt_number` for that task
2. create one new run row
3. set run status to `running`
4. set task status to `running`
5. set agent status to `busy`
6. set `tasks.started_at` if this is the first start for that task
7. set `runs.started_at`
8. emit durable state-transition events

These state changes must happen atomically before the Hermes adapter begins execution.

The run row must bind exactly one task and one agent. The agent on the run must match the task’s assigned agent.

## Stream Handling

While the adapter is active, the runner must:

- append raw output to the run log
- persist or forward enough data for live operator visibility
- emit durable events for meaningful lifecycle changes
- avoid marking the run terminal until the adapter returns a final result

Stream output alone must not mutate task or goal status.

## Terminal Run Handling

When the adapter returns a final result, Pantheon must persist:

- `final_text` into the task result field when the task becomes terminal
- `session_id`
- `exit_code`
- `error_text`
- `usage_json`
- `runs.finished_at`

Then Pantheon must transition state as follows.

### Successful completion

If adapter result status is `complete`:

- mark run `complete`
- mark task `complete`
- set task `completed_at`
- set agent `idle` unless the agent has separately been moved to `disabled` or `error`
- emit `run.completed`
- emit `task.completed`

### Failure

If adapter result status is `failed`:

- mark run `failed`
- mark task `failed`
- set task `completed_at`
- set agent `idle` unless the agent has separately been moved to `disabled` or `error`
- emit `run.failed`
- emit `task.failed`

### Cancellation

If adapter result status is `cancelled`:

- mark run `cancelled`
- mark task `cancelled`
- set task `completed_at`
- set agent `idle` unless the agent has separately been moved to `disabled` or `error`
- emit `run.cancelled`
- emit `task.cancelled`

These terminal transitions must be applied transactionally.

## Event Expectations

Every meaningful state transition must create a durable event row.

The following is Pantheon's proposed canonical V1 event vocabulary required by this contract. These names are bound here for implementation consistency; they are not quoted from a prior enumerated event list.

The runner must emit at least:

- `goal.started`
- `task.started`
- `run.started`
- `run.output`
- `run.completed`
- `run.failed`
- `run.cancelled`
- `task.completed`
- `task.failed`
- `task.cancelled`
- `task.created`
- `goal.completed`
- `goal.completion_blocked`
- `lead.payload_rejected`

Event payloads must be structured JSON with enough identifiers and state data for later inspection.

## Lead-Agent Structured Output Boundary

Only a task executed by the lead agent may trigger control-plane actions from final output.

Worker output:

- may produce normal result text only
- must never create child tasks
- must never complete a goal

Lead output:

- may produce normal result text
- may include one valid `task_proposal` payload
- may include one valid `completion_judgment` payload

Pantheon must:

- persist lead output verbatim before interpretation
- validate payload structure in the control plane
- reject malformed or unauthorized payloads without losing the normal result text

## Child Task Creation Rules

If a lead task returns a valid `task_proposal`, Pantheon must:

- validate every proposed task before creating any of them
- resolve `assigned_agent` to an existing agent in the same group
- resolve `parent_ref` only within the same proposal
- set the parent to the emitting lead task when `parent_ref` is null
- derive child depth from parent depth plus `1`
- create all proposed tasks atomically
- emit one or more `task.created` events

If any proposal entry is invalid, Pantheon must reject the entire proposal and emit `lead.payload_rejected`.

## Goal State Rules

Goal state is a control-plane decision, not a runtime outcome.

A goal may move to `running` when execution starts.

A goal may move to `complete` only when both are true:

- the lead agent emitted a valid `completion_judgment` with `judgment: complete`
- all tasks for the goal are in terminal state

If all tasks are terminal but no valid lead completion judgment exists:

- the goal must not become `complete`
- the goal remains `running` until the operator retries, cancels, or otherwise resolves it

If a lead completion judgment arrives while non-terminal tasks still exist:

- do not complete the goal
- emit `goal.completion_blocked`

Task failure alone does not make a goal terminal. A failed task leaves the goal non-complete until operator action or later valid completion logic resolves the goal.

## Stop Conditions

The active runner loop for a goal stops when one of the following is true:

- the goal becomes `complete`
- the goal becomes `cancelled`
- the operator stops execution
- no eligible work remains and Pantheon returns control to the operator

This contract does not require background scheduling or daemonized execution.

## V1 Exclusions

This contract does not add:

- multi-goal fairness scheduling
- background workers
- distributed dispatch
- speculative retries
- automatic task reassignment
- adapter-side orchestration
