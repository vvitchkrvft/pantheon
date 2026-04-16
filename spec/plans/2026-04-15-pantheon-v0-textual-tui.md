# Pantheon V0 Textual TUI Implementation Plan

> For Hermes: use subagent-driven-development discipline if this gets delegated. Keep the slice small, spec-grounded, and verified with uv.

Goal: replace Pantheon’s empty TUI stub with a real Textual v0 operator shell that launches from `pantheon`, supports top-level screen switching, renders stable panel layouts, and proves read-only inspection against the existing control-plane backend.

Architecture: build a real `Textual` app with explicit screen classes for Pantheon’s top-level operator surfaces instead of one giant conditional UI. Keep the TUI presentation-first and keyboard-centric: all database access stays in `pantheon.db`, screen state is managed with small reactive attributes, top-level navigation uses Textual screen switching rather than homegrown routing, and every core operator action in v0 must be reachable without leaving the keyboard. Start with honest placeholders where needed, but wire real read-only data into the key inspection screens early so the shell is grounded in the actual control plane.

Tech stack: Python 3.11+, uv, Textual, sqlite3 stdlib, pytest, ruff, pyright.

---

## Scope gate

This slice includes only:
- adding Textual as a runtime dependency and syncing the environment
- replacing the current `pantheon` default scaffold printout with a real Textual app launch path
- defining six top-level TUI screens:
  - Overview
  - Agents
  - Goals
  - Tasks
  - Runs
  - Settings
- using Textual-native screen classes, containers, layout, reactivity, and bindings
- implementing stable labeled panel layouts on every top-level screen
- implementing read-only data helpers in `pantheon.db` for TUI snapshots where missing
- wiring real read-only data into at least Agents, Goals, Tasks, and Runs
- wiring partial real read-only data into Overview where practical
- adding focused Textual UI tests for launch, screen switching, and selection/detail synchronization

This slice does not include:
- full mutation-heavy TUI workflows
- agent editing forms
- goal submission forms
- runtime cancellation UI beyond inspection of existing state
- custom widget framework or panel abstraction system
- generic dynamic container infrastructure
- modal stacks unless a narrowly-scoped need appears during implementation
- redesigning Pantheon’s backend orchestration logic

---

## Textual-native design rules

These rules are binding for this slice.

- Use a real `App` subclass as the shell entrypoint.
- Use explicit `Screen` subclasses for the six top-level surfaces.
- Use `switch_screen` for top-level navigation.
- Reserve `push_screen` / `pop_screen` for future drill-ins or modals; do not build around them in v0.
- Use built-in layout/container primitives (`Vertical`, `Horizontal`, `Grid`, scroll containers).
- Let Textual CSS handle proportions and spacing.
- Keep DB access in `pantheon.db`; no inline SQL in screen classes.
- Use small reactive attributes for current selection state.
- Keep highlighted row and selected object synchronized.
- Test the TUI with `run_test()` and pilot-driven interaction tests.

---

## Target repo shape after this slice

Top level:
- `pyproject.toml`
- `uv.lock`
- `README.md`
- `AGENTS.md`
- `spec/`
- `pantheon/`
- `tests/`

Package:
- `pantheon/__init__.py`
- `pantheon/cli.py`
- `pantheon/db.py`
- `pantheon/adapters.py`
- `pantheon/runner.py`
- `pantheon/structured_output.py`
- `pantheon/tui/`
  - `__init__.py`
  - `app.py`
  - `screens/`
    - `__init__.py`
    - `overview.py`
    - `agents.py`
    - `goals.py`
    - `tasks.py`
    - `runs.py`
    - `settings.py`
  - `widgets.py` or `panels.py` only if a tiny shared wrapper is clearly justified
  - `pantheon.tcss`
- `pantheon/tui.py`
  - compatibility entrypoint or thin import shim into `pantheon.tui.app`

Tests:
- `tests/test_cli.py`
- `tests/test_db.py`
- `tests/test_tui.py`

Note: if the TUI package lands cleanly, keep `pantheon/tui.py` as a thin compatibility shim rather than a second implementation file.

---

## Screen model

### Top-level screens

These are the only top-level v0 screens:
- Overview
- Agents
- Goals
- Tasks
- Runs
- Settings

### Navigation model

Top-level screens are peers.

Use app bindings for top-level screen switching:
- `1` -> Overview
- `2` -> Agents
- `3` -> Goals
- `4` -> Tasks
- `5` -> Runs
- `6` -> Settings
- `q` -> quit

Use focus / list navigation inside screens with standard Textual keyboard interaction.

### Startup behavior

On startup:
- if the DB contains one or more groups, launch into Overview with a resolved current group
- if the DB is empty, still launch into Overview and render an explicit empty-state panel
- do not block v0 behind a bootstrap wizard

---

## Screen definitions

### Overview

Purpose: control-plane summary for the current group.

Panels:
- Primary Readout
- Live Feed
- Group Topology
- Agents
- Recent Activity

Recommended layout:
- top row: Primary Readout full width
- middle row: Live Feed | Agents | Group Topology
- bottom row: Recent Activity full width

V0 data target:
- real data for Primary Readout
- real compact agent data for Agents
- real recent events for Recent Activity
- honest placeholder or reduced real data for Live Feed and Group Topology if needed

### Agents

Purpose: inspect the fleet and current per-agent status.

Panels:
- Agent List
- Agent Detail

Layout:
- left: Agent List
- right: Agent Detail

V0 data target:
- fully real read-only data

### Goals

Purpose: inspect top-level goals and their state.

Panels:
- Goal List
- Goal Detail

Layout:
- left: Goal List
- right: Goal Detail

V0 data target:
- fully real read-only data

### Tasks

Purpose: inspect work objects for the current group or selected goal.

Panels:
- Task List
- Task Detail

Layout:
- left: Task List
- right: Task Detail

V0 data target:
- fully real read-only data

### Runs

Purpose: inspect execution attempts and their output metadata.

Panels:
- Run List
- Run Detail / Log Preview

Layout:
- left: Run List
- right: Run Detail / Log Preview

V0 data target:
- fully real read-only data

### Settings

Purpose: surface local Pantheon runtime information and reserve a place for later operator preferences.

Panels:
- App Info
- Database Path
- Runtime Notes
- Future Settings Placeholder

V0 data target:
- mostly static information / placeholders

---

## State model

### App-level reactive state

Keep app-level reactive state minimal:
- `current_group_id`
- `current_screen_name`

### Screen-level reactive state

Each list/detail screen owns its own selection:
- Agents screen: `selected_agent_id`
- Goals screen: `selected_goal_id`
- Tasks screen: `selected_task_id`
- Runs screen: `selected_run_id`

Overview may also carry a small current focus state if needed, but avoid inventing cross-screen selection coupling in v0.

### Synchronization rule

When the highlighted list row changes, update the selected entity immediately and refresh the dependent detail pane from the same snapshot. Do not allow the detail pane to lag behind the highlighted row.

---

## Data access plan

Add or reuse read-only helpers in `pantheon.db` for TUI consumption.

Needed snapshot/helper shapes:
- overview summary for the current group
- list of agents for a group
- detailed agent record by id
- list of goals for a group
- detailed goal record by id
- list of tasks for a group or goal
- detailed task record by id
- list of runs for a group or goal
- detailed run record by id
- recent events for a group or goal

Rules:
- query helpers return simple typed records / dataclasses
- no screen class performs raw SQL
- avoid giant “one object with everything” blobs if narrower helpers keep screens clearer

---

## Widget and layout strategy

Use built-in Textual primitives first.

Preferred building blocks:
- `Header`
- `Footer`
- `Static`
- `Label`
- `ListView`, `OptionList`, or `DataTable` depending on the screen
- `ScrollableContainer`
- `Vertical`
- `Horizontal`
- `Grid`

Avoid in v0:
- custom navigation frameworks
- generic container registries
- over-abstracted reusable panel systems

A tiny shared labeled panel wrapper is acceptable only if duplication becomes obvious across multiple screens.

---

## Styling strategy

Create a single TUI stylesheet, e.g. `pantheon/tui/pantheon.tcss`.

The stylesheet should define:
- shell structure
- panel spacing
- borders
- titles / subtitles
- focus states
- simple grid sizing
- readable empty states

Do not spend this slice on heavy visual ornament.
The goal is a stable operator shell, not a final visual system.

---

## Implementation phases

### Phase 1: Shell and navigation skeleton

Objective: make `pantheon` launch a real Textual shell with six switchable screens.

Files:
- Modify: `pyproject.toml`
- Modify: `pantheon/cli.py`
- Create: `pantheon/tui/__init__.py`
- Create: `pantheon/tui/app.py`
- Create: `pantheon/tui/screens/__init__.py`
- Create: `pantheon/tui/screens/overview.py`
- Create: `pantheon/tui/screens/agents.py`
- Create: `pantheon/tui/screens/goals.py`
- Create: `pantheon/tui/screens/tasks.py`
- Create: `pantheon/tui/screens/runs.py`
- Create: `pantheon/tui/screens/settings.py`
- Create: `pantheon/tui/pantheon.tcss`
- Modify or Create: `pantheon/tui.py`
- Test: `tests/test_tui.py`

Expected outcome:
- `pantheon` launches the app
- header/footer render
- all six screens exist
- keybinding-based screen switching works
- every screen has labeled placeholder panels

### Phase 2: Real read-only inspection screens

Objective: ground the shell in actual Pantheon data.

Files:
- Modify: `pantheon/db.py`
- Modify: `pantheon/tui/screens/overview.py`
- Modify: `pantheon/tui/screens/agents.py`
- Modify: `pantheon/tui/screens/goals.py`
- Modify: `pantheon/tui/screens/tasks.py`
- Modify: `pantheon/tui/screens/runs.py`
- Modify: `tests/test_tui.py`
- Modify: `tests/test_db.py` as needed for new helpers

Expected outcome:
- Agents, Goals, Tasks, and Runs render real read-only data
- Overview renders a real summary and recent activity
- empty states are explicit and readable

### Phase 3: Selection/detail synchronization and polish

Objective: make the shell feel coherent instead of fake.

Files:
- Modify: TUI screen files
- Modify: `pantheon/tui/pantheon.tcss`
- Modify: `tests/test_tui.py`

Expected outcome:
- list movement updates detail panes immediately
- focus and titles are clear
- shell remains deterministic under keyboard navigation

---

## Task breakdown

### Task 1: Add Textual dependency and environment sync

Objective: make the repo capable of running a Textual app.

Files:
- Modify: `pyproject.toml`
- Modify: `uv.lock`

Step 1: Add Textual to runtime dependencies.

Step 2: Run:
`UV_CACHE_DIR=.uv-cache uv sync --group dev`

Expected: dependency resolution succeeds and `uv.lock` updates.

Step 3: Smoke-check import.

Run:
`UV_CACHE_DIR=.uv-cache uv run python -c "import textual"`

Expected: exits 0.

### Task 2: Create the TUI package skeleton

Objective: establish the final package structure before behavior grows.

Files:
- Create: `pantheon/tui/__init__.py`
- Create: `pantheon/tui/app.py`
- Create: `pantheon/tui/screens/__init__.py`
- Create: `pantheon/tui/screens/overview.py`
- Create: `pantheon/tui/screens/agents.py`
- Create: `pantheon/tui/screens/goals.py`
- Create: `pantheon/tui/screens/tasks.py`
- Create: `pantheon/tui/screens/runs.py`
- Create: `pantheon/tui/screens/settings.py`
- Create: `pantheon/tui/pantheon.tcss`
- Modify or Create: `pantheon/tui.py`

Step 1: create the package files with docstrings and import-safe placeholders.

Step 2: verify imports.

Run:
`UV_CACHE_DIR=.uv-cache uv run python -c "import pantheon.tui, pantheon.tui.app, pantheon.tui.screens.overview"`

Expected: exits 0.

### Task 3: Build the Pantheon Textual app shell

Objective: create the real `App` subclass and global screen-switching actions.

Files:
- Modify: `pantheon/tui/app.py`
- Modify: `pantheon/tui/pantheon.tcss`
- Test: `tests/test_tui.py`

Step 1: write a failing test for app launch and default screen.

Step 2: implement `PantheonApp` with:
- title/subtitle
- bindings for screens and quit
- screen installation or named screen registration
- header/footer

Step 3: run the focused test.

Expected: app launches and lands on Overview.

### Task 4: Replace the current CLI default with TUI launch

Objective: make bare `pantheon` launch the Textual app instead of printing the scaffold message.

Files:
- Modify: `pantheon/cli.py`
- Test: `tests/test_cli.py`

Step 1: write a failing CLI test for default launch behavior.

Step 2: route the no-subcommand CLI path into `PantheonApp(...).run()`.

Step 3: keep existing subcommands untouched.

Step 4: run CLI tests.

Expected: non-interactive CLI still works; bare invocation launches the app path.

### Task 5: Create six real screen classes with labeled placeholder panels

Objective: lock the top-level information architecture before real data wiring.

Files:
- Modify: each file in `pantheon/tui/screens/`
- Modify: `pantheon/tui/pantheon.tcss`
- Test: `tests/test_tui.py`

Step 1: write tests asserting screen switching and placeholder panel labels.

Step 2: implement each screen as a `Screen` subclass with a stable layout and panel labels.

Expected: every top-level screen renders with a clearly named layout.

### Task 6: Add read-only DB helpers for TUI snapshots

Objective: give the TUI proper read APIs instead of forcing UI code to improvise.

Files:
- Modify: `pantheon/db.py`
- Test: `tests/test_db.py`

Step 1: identify missing query helpers.

Step 2: add typed read-only helpers for agents, goals, tasks, runs, overview summary, and recent events.

Step 3: test each helper against a temporary database fixture.

Expected: TUI screens can render from DB helpers only.

### Task 7: Wire Agents screen with real list/detail data

Objective: prove the core list/detail pattern against real Pantheon records.

Files:
- Modify: `pantheon/tui/screens/agents.py`
- Modify: `tests/test_tui.py`

Step 1: write a failing TUI test that selects agents and expects detail updates.

Step 2: implement screen-level reactive `selected_agent_id` and synchronized detail rendering.

Step 3: verify keyboard navigation updates the detail pane immediately.

### Task 8: Wire Goals screen with real list/detail data

Objective: establish the same pattern for goals.

Files:
- Modify: `pantheon/tui/screens/goals.py`
- Modify: `tests/test_tui.py`

Step 1: write a failing test for goal selection and detail sync.

Step 2: implement reactive goal selection and detail rendering.

### Task 9: Wire Tasks screen with real list/detail data

Objective: establish the same pattern for tasks.

Files:
- Modify: `pantheon/tui/screens/tasks.py`
- Modify: `tests/test_tui.py`

Step 1: write a failing test for task selection and detail sync.

Step 2: implement reactive task selection and detail rendering.

### Task 10: Wire Runs screen with real list/detail data

Objective: establish the same pattern for runs.

Files:
- Modify: `pantheon/tui/screens/runs.py`
- Modify: `tests/test_tui.py`

Step 1: write a failing test for run selection and detail sync.

Step 2: implement reactive run selection and detail rendering.

### Task 11: Wire Overview with partial real control-plane data

Objective: make the landing screen real enough to be useful.

Files:
- Modify: `pantheon/tui/screens/overview.py`
- Modify: `tests/test_tui.py`

Step 1: render real Primary Readout from overview helpers.

Step 2: render real Recent Activity.

Step 3: render real compact Agents pane.

Step 4: keep Live Feed and Group Topology as honest placeholders if fully live or structural views are not yet worth implementing.

### Task 12: Add Settings screen runtime info

Objective: make Settings honest, even if thin.

Files:
- Modify: `pantheon/tui/screens/settings.py`
- Modify: `tests/test_tui.py`

Step 1: render app/runtime information and placeholder settings areas.

Step 2: verify the screen is labeled and stable.

### Task 13: Tighten styling and empty states

Objective: make the shell readable under real use.

Files:
- Modify: `pantheon/tui/pantheon.tcss`
- Modify: screen files as needed
- Modify: `tests/test_tui.py`

Step 1: tune panel spacing, borders, titles, and focus treatment.

Step 2: make empty database / empty list states explicit.

Step 3: verify no panel becomes visually ambiguous.

---

## Test plan

Create `tests/test_tui.py` with these minimum tests:
- app launches successfully
- default screen is Overview
- screen switching bindings work for all six screens
- each screen renders its expected labeled panels
- Agents selection updates Agent Detail
- Goals selection updates Goal Detail
- Tasks selection updates Task Detail
- Runs selection updates Run Detail
- empty-state startup renders explicitly when no groups exist

Verification commands after meaningful slices:
1. `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_tui.py -q`
2. `UV_CACHE_DIR=.uv-cache uv run pytest`
3. `UV_CACHE_DIR=.uv-cache uv run ruff check .`
4. `UV_CACHE_DIR=.uv-cache uv run pyright`

---

## Definition of done

This slice is done when:
- `pantheon` launches a real Textual app
- all six top-level screens exist as real `Screen` classes
- screen switching works through bindings
- every screen has a stable labeled layout
- Agents, Goals, Tasks, and Runs render real read-only Pantheon data
- Overview renders a real summary and recent activity
- selection and detail panes stay synchronized
- TUI tests pass along with full repo verification

---

## Follow-on work deliberately deferred

After this slice, likely next work will include:
- group switching UX
- goal submit flow in the TUI
- richer overview topology / live feed behavior
- drill-in screens or modal detail flows
- operator actions such as retry/cancel from the TUI
- more robust settings and configuration surfaces

None of that belongs in this first v0 shell slice unless the current implementation proves the plan wrong.