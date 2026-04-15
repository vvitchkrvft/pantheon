1. Pantheon identity

Pantheon is a local control plane for running a group of Hermes agents from the terminal.

Pantheon is not an agent. It does not think, plan, or improvise on its own. It persists state, dispatches work, supervises execution, and exposes the results to the operator.

Pantheon is terminal-first. The primary product is a TUI. The CLI exists to launch, bootstrap, and inspect. There is no web frontend in V1.

Pantheon is local-first. One machine. One operator. One SQLite database. Hermes does the work. Pantheon runs the system around it.

2. Core principles (non-negotiable invariants)

- Pantheon is a control plane, not an execution engine.
  Hermes remains the runtime. Pantheon never becomes a second agent framework.

- SQLite is the source of truth.
  Goals, tasks, runs, events, and outputs live in Pantheon’s database. Not in scattered runtime files.

- The adapter boundary is strict.
  Pantheon talks to Hermes only through a defined adapter surface. No orchestration logic leaks into Hermes internals.

- Work and execution are separate.
  A task is a work object. A run is an execution attempt. They are not the same thing.

- Each agent is isolated.
  Every managed Hermes agent has its own workspace and its own HERMES_HOME.

- One active run per agent.
  No concurrent execution on the same Hermes profile in V1.

- The operator is explicit.
  Pantheon does not hide state transitions behind magic. Start, stop, inspect, retry, and cancel are visible control-plane actions.

- The audit trail is mandatory.
  Every meaningful state transition produces a durable event.

- Terminal-first means terminal-first.
  The full core loop must work from the TUI and CLI alone.

- V1 stays small.
  Fewer tables. Fewer services. Fewer abstractions. No product theater.

3. What Pantheon adopts from adjacent reference systems

- Hermes-specific control-plane framing.
  Pantheon is built around orchestrating Hermes agents, not arbitrary runtimes.

- Per-agent runtime isolation.
  Separate workspace, separate HERMES_HOME, separate execution envelope for each agent.

- A direct runtime boundary.
  Pantheon prepares invocation context, launches Hermes, streams output, captures result, and persists it.

- Operational supervision.
  Agent status, task status, run status, and live logs are first-class control-plane concerns.

- Real-time operator visibility.
  Execution progress must be watchable while it happens.

- Simple runtime ownership.
  Pantheon owns orchestration state. Hermes owns execution.

- Reusable operator grammar, translated to terminal form.
  The useful operator shape is overview, fleet, detail, live feed, ledger, and workspace/log inspection. Pantheon should translate those operator patterns into its own TUI instead of copying a browser product.

4. What Pantheon adopts from Paperclip

- Separation of task from run.
  A task represents work. A run represents one attempt to do that work.

- Goal-linked work structure.
  Work exists in service of a goal. Pantheon keeps that chain explicit.

- Atomic dispatch discipline.
  Claiming work and starting runs must be consistent. No double-starts. No vague ownership.

- Event-led audit model.
  State changes are logged as structured control-plane events, not buried in prose.

- Operator workflow clarity.
  Submit work, watch execution, inspect artifacts, read history.

- Tight orchestration semantics.
  Queueing, claiming, terminal states, retries, and completion are control-plane rules, not loose conventions.

5. What Pantheon rejects

- Web dashboards as the primary product
- Multi-user systems
- RBAC, auth stacks, and tenancy layers
- Distributed execution and remote node management
- Company, board, CEO, project-management theater
- Budget systems
- Approval systems
- Plugin platforms
- Generic multi-runtime orchestration in V1
- Managed integrations catalogs
- Knowledge promotion systems
- Skill promotion or self-improvement systems
- Embedded complexity disguised as “future-proofing”
- Product nouns that do not directly serve the control-plane loop

Pantheon rejects both failure modes:
- browser-cockpit sprawl around the runtime
- Paperclip’s company simulator

The rule is simple:
- take useful mechanics from adjacent systems
- do not inherit their product shape
- take Paperclip’s orchestration semantics
- do not take Paperclip’s company theater

6. V1 scope definition

Pantheon V1 is responsible for exactly this:

- defining and saving a group of Hermes agents
- storing agent runtime configuration needed to invoke them
- accepting a goal from the operator
- creating and tracking tasks under that goal
- dispatching tasks to Hermes agents through a strict adapter
- enforcing one active run per agent
- streaming live run output to the terminal
- persisting task results, run history, and event history
- showing current state and final state in the TUI
- letting the operator inspect any goal, task, run, log, or output

Pantheon V1 owns:
- groups
- agents
- goals
- tasks
- runs
- events
- terminal operator surface

That is the product.

7. V1 non-goals

Pantheon V1 does not do:

- web UI
- multi-user access
- remote workers or multiple machines
- non-Hermes adapters
- cron scheduling
- approvals
- budgets
- project/workspace management subsystems
- plugin loading
- skill sharing or promotion
- memory or knowledge promotion
- self-modification
- autonomous governance
- background product abstractions beyond the control-plane loop

If a feature does not directly improve:
create/load group → submit goal → start execution → watch runs → inspect outputs

it is out of scope.
