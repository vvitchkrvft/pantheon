1. Product statement

Pantheon V1 is a local, terminal-first control plane for running a saved group of Hermes agents against a user-submitted goal. It owns orchestration state, task dispatch, run supervision, live terminal visibility, and final inspection. Hermes remains the execution runtime. Pantheon is the system around the agents, not the agent itself.

2. Hard constraints (must-follow rules)

- Pantheon is not an agent.
- Hermes is the only runtime in V1.
- No web UI.
- No multi-user system.
- No distributed or remote execution.
- No plugin system.
- No event bus framework.
- No budgets, approvals, projects, or company abstractions.
- No knowledge promotion, skill promotion, or self-improvement systems.
- SQLite is the only source of truth.
- One active run per agent.
- Every managed agent has its own workspace and its own HERMES_HOME.
- A task is a work object. A run is an execution attempt. They must be separate.
- The full product loop must work from `pantheon` without writing Python code.
- The TUI is the primary surface. The CLI is secondary and must stay thin.

3. Core components (only what is required)

- SQLite store
  - Persists groups, agents, goals, tasks, runs, and events.

- Hermes adapter
  - Starts Hermes for one task.
  - Streams output.
  - Returns final result and run metadata.

- Orchestrator
  - Claims queued tasks.
  - Starts runs for idle agents.
  - Applies structured outputs.
  - Advances goal state.

- Structured output parser
  - Accepts control payloads only from the lead agent.
  - Creates child tasks.
  - Marks goal completion when valid.

- TUI
  - Group setup/load.
  - Goal submission.
  - Start execution.
  - Live status.
  - Task/run inspection.
  - Group/agent detail views that translate useful operator patterns into terminal form: overview, fleet, detail, live feed, ledger, and workspace/log inspection.

- CLI
  - Launch TUI.
  - Minimal non-interactive setup and inspection commands.

4. Execution model (how a goal actually runs)

- A group is a saved set of Hermes agents.
- Each group has exactly one lead agent and zero or more worker agents.
- A goal belongs to one group.
- Submitting a goal creates one root task assigned to the lead agent.
- Starting execution activates the runner loop.
- The runner loop finds queued tasks and assigns them to idle agents.
- Each task execution creates a run row.
- The Hermes adapter executes the task and streams run output.
- Worker agents return normal task output only.
- The lead agent may return:
  - normal output
  - task proposals for child tasks
  - a completion judgment
- Pantheon persists all outputs verbatim.
- Pantheon only creates child tasks from valid lead-agent control payloads.
- A goal completes only when:
  - the lead agent emits `completion_judgment` with `judgment: complete`
  - all tasks for the goal are in terminal state

5. Golden path (user workflow from start to finish)

1. Run `pantheon`
2. Create a group or load an existing group
3. Add or edit agents in the group
   - one lead
   - optional workers
4. Submit a goal
5. Start execution
6. Watch live task and run activity
7. Inspect task outputs and run logs
8. Reach terminal goal state
9. Review final goal state and outputs

This must work entirely from the TUI.

6. Minimal data model (tables and fields)

groups
- id
- name
- created_at
- updated_at

agents
- id
- group_id
- name
- role                -- lead | worker
- profile_name        -- Hermes profile name or null
- hermes_home
- workdir
- model_override      -- nullable
- provider_override   -- nullable
- status              -- idle | busy | disabled | error
- created_at
- updated_at

goals
- id
- group_id
- title
- status              -- draft | queued | running | complete | failed | cancelled
- root_task_id        -- nullable until root task exists
- started_at          -- nullable
- completed_at        -- nullable
- created_at
- updated_at

tasks
- id
- goal_id
- parent_task_id      -- nullable
- assigned_agent_id
- title
- input_text
- result_text         -- nullable
- status              -- queued | running | complete | failed | cancelled
- priority            -- integer default 5
- depth               -- integer default 0
- created_at
- started_at          -- nullable
- completed_at        -- nullable
- updated_at

runs
- id
- task_id
- agent_id
- attempt_number
- status              -- queued | running | complete | failed | cancelled
- session_id          -- nullable
- pid                 -- nullable
- exit_code           -- nullable
- error_text          -- nullable
- log_path
- usage_json          -- nullable
- started_at          -- nullable
- finished_at         -- nullable
- created_at

events
- id
- goal_id             -- nullable
- task_id             -- nullable
- run_id              -- nullable
- agent_id            -- nullable
- event_type
- payload_json
- created_at

Required invariants
- Each group must have exactly one lead agent.
- Only one run may be active per agent.
- Task parent must belong to the same goal.
- Root task depth is 0. Child task depth is parent depth + 1.
- A run belongs to exactly one task and one agent.
- Goal completion requires all tasks terminal and valid lead completion judgment.

7. Hermes adapter contract

Single interface for V1:

run_task(agent, task, run_context) -> stream + final_result

Agent input
- agent_id
- name
- role
- profile_name
- hermes_home
- workdir
- model_override
- provider_override

Task input
- task_id
- goal_id
- title
- input_text

Run context input
- run_id
- parent_task_summary      -- optional compact text for child tasks
- dependency_outputs       -- optional list of prior task outputs if needed
- operator_note            -- optional, nullable

Streaming output events
- stdout text chunks
- stderr text chunks
- structured JSON chunk if emitted by Hermes final output handling
- adapter lifecycle events:
  - started
  - exited
  - failed

Final result
- status                   -- complete | failed | cancelled
- final_text
- session_id               -- nullable
- exit_code                -- nullable
- error_text               -- nullable
- usage_json               -- nullable

Adapter rules
- Adapter owns process invocation only.
- Adapter does not mutate Pantheon state directly.
- Adapter does not inspect Pantheon DB.
- Adapter writes full raw run log to `log_path`.
- Adapter must support streaming output while the run is active.
- Adapter must launch Hermes with the agent’s own workspace and HERMES_HOME.

8. Structured output contract (lead + worker behavior)

Only the lead agent may emit control payloads.

Workers
- Receive task input
- Return normal text output only
- Must not emit control payloads

Lead
- May return normal text output
- May append exactly one JSON control payload block
- Supported payload types in V1:

A. task_proposal
{
  "output_type": "task_proposal",
  "tasks": [
    {
      "ref": "t1",
      "title": "Short task title",
      "input_text": "Concrete instruction",
      "assigned_agent": "worker-name-or-id",
      "parent_ref": null
    }
  ]
}

Rules:
- `ref` must be unique within the proposal.
- `assigned_agent` must resolve to an existing group agent.
- If `parent_ref` is null, parent is the lead task that emitted the proposal.
- If `parent_ref` is set, it must resolve to another task ref in the same proposal.
- Pantheon creates all proposed tasks atomically or rejects the whole payload.

B. completion_judgment
{
  "output_type": "completion_judgment",
  "judgment": "complete"
}

Rules:
- Only accepted from the lead.
- Only marks goal complete if all tasks are terminal.
- If tasks remain non-terminal, store an event and ignore the state transition.

Parsing rules
- Pantheon does not route on prose.
- Pantheon routes only on `output_type`.
- Malformed payloads are rejected and logged as events.
- Normal text output is still stored even if a payload is rejected.

9. Runner loop behavior (step-by-step)

1. Load goal and group
2. Mark goal `running` if not already running
3. Find all agents with no active run
4. Find queued tasks whose assigned agent is idle
5. Pick tasks in this order:
   - lower depth first
   - lower priority number first
   - earlier created_at first
6. For each eligible task:
   - create new run row with incremented attempt_number
   - mark run `running`
   - mark agent `busy`
   - mark task `running`
   - write task.started and run.started events
   - invoke Hermes adapter
7. While adapter streams:
   - append chunks to run log
   - emit run.output events
   - refresh TUI state
8. When adapter finishes:
   - persist final_text, session_id, exit_code, error_text, usage_json
   - mark run terminal
   - mark agent `idle` unless agent disabled/error
   - mark task `complete` or `failed`
   - write task.completed/task.failed and run.completed/run.failed events
9. If the completed task belongs to the lead:
   - parse structured payload from final_text
   - if valid task_proposal: create child tasks atomically and emit task.created events
   - if valid completion_judgment and all tasks terminal: mark goal complete and emit goal.completed
10. If all tasks are terminal and no valid completion judgment exists:
   - leave goal in `running` unless lead task is retried
11. If any run fails:
   - task becomes `failed`
   - goal remains `running` unless operator cancels or retries
12. Loop continues until:
   - goal `complete`
   - goal `cancelled`
   - operator stops execution

No scheduler. No background automation beyond the active runner loop.

10. CLI surface (exact commands)

Required commands only:

- `pantheon`
  - Launch the TUI

- `pantheon group init <name>`
  - Create a new group

- `pantheon group list`
  - List groups

- `pantheon agent add`
  - Interactive add-agent flow
  - Required args or prompts:
    - group
    - name
    - role
    - hermes_home
    - workdir
    - profile_name optional
    - model_override optional
    - provider_override optional

- `pantheon goal submit "<goal text>" --group <group-name-or-id>`
  - Create goal and root lead task

- `pantheon start <goal-id>`
  - Start runner loop for one goal

- `pantheon status <goal-id>`
  - Print compact goal/task/run status

- `pantheon inspect task <task-id>`
  - Print task details and latest result

- `pantheon inspect run <run-id>`
  - Print run metadata and log path

- `pantheon retry task <task-id>`
  - Set failed task back to queued if agent is enabled and goal not terminal

- `pantheon cancel goal <goal-id>`
  - Mark goal cancelled and stop new runs from starting

No other commands in V1.

11. TUI surface (exact screens and actions)

Screen 1: Group picker
Shows
- groups list
Actions
- create group
- open group
- delete group

Screen 2: Group detail
Shows
- group name
- lead agent
- worker agents
Actions
- add agent
- edit agent
- disable/enable agent
- submit goal
- back

Screen 3: Agent editor
Fields
- name
- role
- profile_name
- hermes_home
- workdir
- model_override
- provider_override
Actions
- save
- cancel

Screen 4: Goal submit
Fields
- goal text
Actions
- submit
- cancel

Screen 5: Goal detail / execution view
Shows
- goal title and status
- task tree
- selected task detail
- current active runs
- live log pane for selected run
Actions
- start execution
- cancel goal
- retry selected task
- inspect selected run
- refresh
- back

Screen 6: Task detail panel
Shows
- task title
- assigned agent
- status
- input_text
- result_text
- run history
Actions
- retry task
- view run
- back

Screen 7: Run detail panel
Shows
- run status
- attempt number
- agent
- started_at / finished_at
- exit_code
- session_id
- full log path
- live or completed log content
Actions
- back

TUI rules
- Starting `pantheon` lands in the group picker.
- A user can complete the full MVP flow without touching the CLI.
- Live execution view must update while runs are active.
- All actions must map directly to DB state transitions and events.
- The TUI should translate useful operator patterns into a local terminal surface: overview, fleet, detail, live feed, ledger, and workspace/log inspection.

12. Definition of done (what proves V1 works)

V1 is done when all of the following are true:

- A user can run `pantheon` and complete the entire core loop in the TUI:
  - create or load a group
  - add agents
  - submit a goal
  - start execution
  - watch it live
  - inspect outputs

- SQLite persists all core state:
  - groups
  - agents
  - goals
  - tasks
  - runs
  - events

- Each agent executes with its own workspace and HERMES_HOME.

- The lead agent can create child tasks through valid structured output.

- Worker agents complete assigned tasks and return plain output.

- The runner loop enforces one active run per agent.

- Live output is visible while a run is active.

- A user can inspect:
  - task input
  - task result
  - run status
  - run log
  - final goal state

- Goal completion requires:
  - valid lead completion judgment
  - all tasks terminal

- Failed runs are visible and inspectable.
- Failed tasks can be retried by operator action.
- No Python scripting is required anywhere in the user workflow.

If any part of the core loop depends on a browser, a plugin, a scheduler, a second user, or hand-written Python glue, V1 is not done.
