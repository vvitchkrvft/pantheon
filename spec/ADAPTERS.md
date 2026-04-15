# Pantheon Hermes Adapter Contract

## Purpose

Pantheon is the control plane. Hermes is the agent execution runtime.

This document defines the only V1 adapter boundary Pantheon may use to execute agent work. The adapter is a narrow process-invocation boundary. It must not absorb control-plane policy, database access, or orchestration logic.

## Ownership Boundary

Pantheon owns:

- persisted orchestration state
- task selection
- run creation
- agent busy or idle state
- goal state transitions
- event creation
- structured payload validation
- operator-facing status and inspection

Hermes, through the Pantheon adapter, owns:

- process launch for one task execution
- streaming process output
- surfacing process exit details
- returning final execution result metadata

The adapter is not an orchestrator. It executes one task for one agent in one run context.

## V1 Interface

V1 exposes a single adapter operation:

```text
run_task(agent, task, run_context) -> stream + final_result
```

The concrete Python signature may vary, but the semantic input and output shape below is binding.

## Input Contract

### Agent Input

Required fields:

- `agent_id`
- `name`
- `role`
- `profile_name`
- `hermes_home`
- `workdir`
- `model_override`
- `provider_override`

Rules:

- `role` must be either `lead` or `worker`
- `hermes_home` must be the agent-specific Hermes home path
- `workdir` must be the agent-specific workspace path
- overrides may be null

### Task Input

Required fields:

- `task_id`
- `goal_id`
- `title`
- `input_text`

Rules:

- `input_text` is the concrete task instruction passed to Hermes
- the adapter must treat task input as opaque Pantheon-provided content

### Run Context Input

Required fields:

- `run_id`

Optional fields:

- `parent_task_summary`
- `dependency_outputs`
- `operator_note`
- `log_path`

Rules:

- `parent_task_summary` is compact contextual text for child tasks
- `dependency_outputs` is a Pantheon-supplied list of prior task outputs when Pantheon chooses to provide them
- `operator_note` is nullable operator-provided context
- `log_path` is the Pantheon-selected destination for the raw run log

## Streaming Output Contract

The adapter must emit a stream while the Hermes execution is active.

Allowed stream event categories:

- `stdout`
  - raw text chunk from Hermes standard output
- `stderr`
  - raw text chunk from Hermes standard error
- `structured_output`
  - structured JSON chunk only if Hermes exposes one separately from plain text
- `lifecycle`
  - adapter lifecycle event with subtype:
    - `started`
    - `exited`
    - `failed`

Rules:

- streaming must preserve observed event order
- text chunks must not be reinterpreted as Pantheon state transitions inside the adapter
- the adapter may expose structured output separately, but Pantheon remains responsible for deciding whether it is valid and actionable
- raw text output must still be available for durable logging even if structured parsing later fails

## Final Result Contract

When execution terminates, the adapter must return a final result object with these fields:

- `status`
  - one of `complete`, `failed`, or `cancelled`
- `final_text`
  - terminal text output captured for the run
- `session_id`
  - nullable Hermes session identifier
- `exit_code`
  - nullable process exit code
- `error_text`
  - nullable terminal error summary
- `usage_json`
  - nullable structured usage payload serialized or represented as data

Rules:

- `status` reflects runtime execution outcome only
- `final_text` may include prose and the lead-agent control payload block
- `error_text` must be populated when the adapter itself or the Hermes process fails in a way Pantheon should surface
- `usage_json` is optional and must not be required for success

## Non-Negotiable Adapter Rules

The adapter must not:

- mutate Pantheon database state directly
- inspect Pantheon tables or derive orchestration state from SQLite
- select tasks
- create runs
- mark tasks, goals, or agents terminal
- decide goal completion
- create child tasks from lead output

The adapter must:

- run Hermes using the agent’s own `workdir`
- run Hermes using the agent’s own `HERMES_HOME`
- support one-task-at-a-time invocation
- write or allow Pantheon to write the full raw run log to `log_path`
- surface failures as adapter results or lifecycle events rather than swallowing them

## Failure Semantics

The adapter boundary must distinguish:

- execution failure
  - Hermes started but terminated unsuccessfully
- adapter failure
  - Pantheon could not launch or supervise Hermes correctly
- cancellation
  - Pantheon requested termination and the adapter observed cancellation

Pantheon, not the adapter, decides how those runtime outcomes affect task, run, agent, and goal records.

## V1 Exclusions

This contract does not add:

- non-Hermes adapters
- remote execution transports
- adapter-side retries
- adapter-side scheduling
- adapter-side goal logic
